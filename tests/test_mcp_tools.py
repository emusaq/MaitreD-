import unittest
import os
os.environ["SQLALCHEMY_CREATE_ALL"] = "0"
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import Depends

from mcp.mcp_server import list_open_times, check_availability, create_reservation, ALLOWED_TOOLS
from models.models import Base, Client


class DummyDep:
    def __init__(self, db):
        self.db = db
    def __call__(self):
        yield self.db


class MCPToolsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        # Ensure minimal reservations table exists for SQLite tests
        self.db.execute(text(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_iso TEXT NOT NULL,
                time_24h TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                slot_id TEXT NOT NULL UNIQUE,
                client_id INTEGER
            )
            """
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_allowed_tools_only(self):
        self.assertEqual(ALLOWED_TOOLS, {"list_open_times", "check_availability", "create_reservation"})
        # Ensure removed/forbidden tools are not present
        self.assertFalse(hasattr(__import__('mcp.mcp_server', fromlist=['']), 'upsert_reservation'))

    def test_create_reservation_without_client_ref(self):
        # No PII in output
        # list_open_times
        data = type('obj', (), {'date_iso': '2025-01-02', 'party_size': 2})
        _ = asyncio.run(list_open_times(data, self.db))

        # check_availability and create reservation
        chk_in = type('obj', (), {'date_iso': '2025-01-02', 'time_24h': '17:00', 'party_size': 2})
        _ = asyncio.run(check_availability(chk_in, self.db))

        crt_in = type('obj', (), {'slot_id': '2025-01-02_17:00', 'party_size': 2, 'client_ref': None})
        result = asyncio.run(create_reservation(crt_in, self.db))
        self.assertIn('reservation_id', result)
        self.assertNotIn('name', result)
        self.assertNotIn('phone', result)
        self.assertNotIn('email', result)

    def test_create_reservation_with_client_ref(self):
        # Insert a client row
        c = Client(first_name='A', last_name='B', phone_number='000', email=None)
        self.db.add(c)
        self.db.commit()

        crt_in = type('obj', (), {'slot_id': '2025-01-03_18:00', 'party_size': 4, 'client_ref': c.client_id})
        result = asyncio.run(create_reservation(crt_in, self.db))
        self.assertEqual(result['slot_id'], '2025-01-03_18:00')
        # Ensure reservation row was created & associated
        row = self.db.execute(text("SELECT client_id FROM reservations WHERE slot_id='2025-01-03_18:00'"))
        cid = row.fetchone()[0]
        self.assertEqual(cid, c.client_id)


if __name__ == '__main__':
    unittest.main()
