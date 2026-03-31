import os
import sqlite3
import unittest

from sqlalchemy import create_engine

os.environ["SQLALCHEMY_CREATE_ALL"] = "0"

from database.schema_checks import find_staff_portal_schema_inconsistencies
from models.models import Base


class DatabaseSchemaConsistencyTests(unittest.TestCase):
    def tearDown(self):
        for path in ("./test_db_consistency_ok.db", "./test_db_consistency_legacy.db"):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_current_schema_contains_columns_staff_portal_needs(self):
        engine = create_engine(
            "sqlite:///./test_db_consistency_ok.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)

        issues = find_staff_portal_schema_inconsistencies(engine)

        self.assertEqual(issues, [])

    def test_legacy_like_schema_is_flagged_for_staff_portal_breakage(self):
        db_path = "./test_db_consistency_legacy.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE reservations (
                    id INTEGER PRIMARY KEY,
                    date_iso DATE NOT NULL,
                    time_24h TIME NOT NULL,
                    party_size INTEGER NOT NULL,
                    slot_id TEXT NOT NULL,
                    client_id INTEGER
                );

                CREATE TABLE reservation_settings (
                    id INTEGER PRIMARY KEY,
                    reservations_enabled BOOLEAN NOT NULL DEFAULT 1,
                    open_from TIME NOT NULL DEFAULT '17:00',
                    open_to TIME NOT NULL DEFAULT '21:00',
                    slot_interval INTEGER NOT NULL DEFAULT 30,
                    max_per_slot INTEGER NOT NULL DEFAULT 20,
                    max_party_size INTEGER NOT NULL DEFAULT 8
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        issues = find_staff_portal_schema_inconsistencies(engine)

        self.assertTrue(any(issue.startswith("reservations missing columns:") for issue in issues))
        self.assertTrue(any("status" in issue for issue in issues))
        self.assertTrue(any(issue.startswith("reservation_settings missing columns:") for issue in issues))
        self.assertTrue(any("deny_message" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
