import unittest
import os
os.environ["SQLALCHEMY_CREATE_ALL"] = "0"
import asyncio
from datetime import time as dt_time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from mcp.mcp_server import list_open_times, check_availability, create_reservation, ALLOWED_TOOLS
from models.models import Base, Client, ReservationSettings


_RESERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS reservations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date_iso    TEXT NOT NULL,
    time_24h    TEXT NOT NULL,
    party_size  INTEGER NOT NULL,
    slot_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    guest_name  TEXT,
    occasion    TEXT,
    guest_phone TEXT,
    note        TEXT,
    note_author TEXT,
    client_id   INTEGER
)
"""


class MCPToolsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.execute(text(_RESERVATIONS_DDL))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_allowed_tools_only(self):
        self.assertEqual(ALLOWED_TOOLS, {"list_open_times", "check_availability", "create_reservation"})
        self.assertFalse(hasattr(__import__('mcp.mcp_server', fromlist=['']), 'upsert_reservation'))

    def test_create_reservation_without_client_ref(self):
        data = type('obj', (), {'date_iso': '2025-01-02', 'party_size': 2})
        _ = asyncio.run(list_open_times(data, self.db))

        chk_in = type('obj', (), {'date_iso': '2025-01-02', 'time_24h': '17:00', 'party_size': 2})
        _ = asyncio.run(check_availability(chk_in, self.db))

        crt_in = type('obj', (), {'slot_id': '2025-01-02_17:00', 'party_size': 2, 'client_ref': None})
        result = asyncio.run(create_reservation(crt_in, self.db))
        self.assertIn('reservation_id', result)
        self.assertNotIn('name', result)
        self.assertNotIn('phone', result)
        self.assertNotIn('email', result)

    def test_create_reservation_with_client_ref(self):
        c = Client(first_name='A', last_name='B', phone_number='000', email=None)
        self.db.add(c)
        self.db.commit()

        crt_in = type('obj', (), {'slot_id': '2025-01-03_18:00', 'party_size': 4, 'client_ref': c.client_id})
        result = asyncio.run(create_reservation(crt_in, self.db))
        self.assertEqual(result['slot_id'], '2025-01-03_18:00')
        row = self.db.execute(text("SELECT client_id FROM reservations WHERE slot_id='2025-01-03_18:00'"))
        cid = row.fetchone()[0]
        self.assertEqual(cid, c.client_id)

    # ------------------------------------------------------------------
    # Regression: slot validation
    # ------------------------------------------------------------------

    def test_invalid_slot_format_rejected(self):
        """create_reservation must reject malformed slot_ids."""
        from fastapi import HTTPException
        for bad in ["not-a-slot", "2025-13-01_17:00", "2025-01-02T17:00"]:
            with self.assertRaises(HTTPException) as ctx:
                crt_in = type('obj', (), {'slot_id': bad, 'party_size': 2, 'client_ref': None})
                asyncio.run(create_reservation(crt_in, self.db))
            self.assertEqual(ctx.exception.status_code, 422, f"Expected 422 for slot_id={bad!r}")

    def test_slot_outside_hours_rejected(self):
        """Slots outside configured business hours must be rejected."""
        from fastapi import HTTPException
        # Default settings: 17:00–21:00
        crt_in = type('obj', (), {'slot_id': '2025-01-02_10:00', 'party_size': 2, 'client_ref': None})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(create_reservation(crt_in, self.db))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_slot_misaligned_to_interval_rejected(self):
        """Slots that don't align to the configured interval must be rejected."""
        from fastapi import HTTPException
        # Default settings: interval=30 — 17:15 is not on a 30-min boundary
        crt_in = type('obj', (), {'slot_id': '2025-01-02_17:15', 'party_size': 2, 'client_ref': None})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(create_reservation(crt_in, self.db))
        self.assertEqual(ctx.exception.status_code, 422)

    # ------------------------------------------------------------------
    # Regression: overbooking prevention
    # ------------------------------------------------------------------

    def test_second_booking_exceeding_capacity_fails(self):
        """A second booking that pushes the slot over max_per_slot must fail."""
        from fastapi import HTTPException
        # Insert custom settings: max_per_slot=4, so two party-of-3 requests can't both succeed
        settings = ReservationSettings(
            reservations_enabled=True,
            open_from=dt_time(17, 0),
            open_to=dt_time(21, 0),
            slot_interval=30,
            max_per_slot=4,
            max_party_size=8,
        )
        self.db.add(settings)
        self.db.commit()

        slot = '2025-06-01_18:00'

        # First booking: party of 3 — should succeed (3 <= 4)
        crt1 = type('obj', (), {'slot_id': slot, 'party_size': 3, 'client_ref': None})
        result1 = asyncio.run(create_reservation(crt1, self.db))
        self.assertIn('reservation_id', result1)

        # Second booking: party of 3 — should fail (3+3=6 > 4)
        crt2 = type('obj', (), {'slot_id': slot, 'party_size': 3, 'client_ref': None})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(create_reservation(crt2, self.db))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_second_booking_within_capacity_succeeds(self):
        """Multiple bookings are allowed as long as combined party_size stays under max_per_slot."""
        settings = ReservationSettings(
            reservations_enabled=True,
            open_from=dt_time(17, 0),
            open_to=dt_time(21, 0),
            slot_interval=30,
            max_per_slot=10,
            max_party_size=8,
        )
        self.db.add(settings)
        self.db.commit()

        slot = '2025-06-02_19:00'
        crt1 = type('obj', (), {'slot_id': slot, 'party_size': 4, 'client_ref': None})
        result1 = asyncio.run(create_reservation(crt1, self.db))
        self.assertIn('reservation_id', result1)

        crt2 = type('obj', (), {'slot_id': slot, 'party_size': 4, 'client_ref': None})
        result2 = asyncio.run(create_reservation(crt2, self.db))
        self.assertIn('reservation_id', result2)


if __name__ == '__main__':
    unittest.main()
