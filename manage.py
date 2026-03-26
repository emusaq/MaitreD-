import argparse
import importlib
from contextlib import closing

from database.connection import connect
from database.schema import initialize_database
from models.models import SessionLocal, ReservationSettings, Employee
from models.employees import hash_password


def is_initialized(conn) -> bool:
    """Check if the 'clients' table exists in the public schema."""
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT to_regclass('public.clients');")
        result = cur.fetchone()
        return result is not None and result[0] is not None


def wipe_schema(conn) -> None:
    """Drop and recreate the public schema using raw SQL."""
    with closing(conn.cursor()) as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
        cur.execute("CREATE SCHEMA public;")
        cur.execute("GRANT ALL ON SCHEMA public TO public;")
    conn.commit()
    print("🗑️  Existing schema dropped and public schema recreated.")


def seed_reservation_settings() -> None:
    """Insert a default reservation_settings row if none exists."""
    db = SessionLocal()
    try:
        if db.query(ReservationSettings).count() == 0:
            db.add(ReservationSettings(
                reservations_enabled=True,
                open_from="17:00",
                open_to="21:00",
                slot_interval=30,
                max_per_slot=20,
                max_party_size=8,
                large_party_threshold=8,
                large_party_phone="",
                confirm_message="Your reservation at Garufa has been confirmed. We look forward to welcoming you.",
                deny_message="We regret we are unable to accommodate your request at this time. Please contact us directly for assistance.",
                cancel_message="Your reservation at Garufa has been cancelled. We apologize for any inconvenience.",
            ))
            db.commit()
            print("✅ Default reservation_settings seeded.")
        else:
            print("ℹ️  reservation_settings already present — skipping seed.")
    finally:
        db.close()


def seed_test_employee() -> None:
    """Insert a default test employee (admin/admin) if it doesn't exist."""
    db = SessionLocal()
    try:
        if db.query(Employee).filter_by(username="admin").first() is None:
            db.add(Employee(
                first_name="Admin",
                last_name="User",
                role="owner",
                access_code=1234,
                username="admin",
                password=hash_password("admin"),
            ))
            db.commit()
            print("✅ Test employee seeded — username: admin / password: admin")
        else:
            print("ℹ️  Test employee already present — skipping.")
    finally:
        db.close()


def run_basic_tests() -> None:
    """Run lightweight sanity tests (e.g., module import tests)."""
    print("\n🏃 Running basic sanity tests …")
    tests = [
        ("models.client import", lambda: importlib.import_module("models.client")),
    ]
    passed, failed = 0, 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"✅ {desc}")
            passed += 1
        except Exception as exc:
            print(f"❌ {desc}: {exc}")
            failed += 1
    print(f"\nTests finished — {passed} passed, {failed} failed.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize, reset, and test the MaitreD database."
    )
    parser.add_argument(
        "--reset", action="store_true", help="Wipe existing schema and re‑initialize."
    )
    args = parser.parse_args()

    try:
        conn = connect()
        print("✅ Database connection successful.")

        if args.reset:
            wipe_schema(conn)
            initialize_database()
            seed_reservation_settings()
            seed_test_employee()
            print("✅ Database reset & re‑initialized.")
        else:
            if not is_initialized(conn):
                initialize_database()
                seed_reservation_settings()
                seed_test_employee()
                print("✅ Database initialized successfully.")
            else:
                seed_test_employee()
                print("ℹ️  Database already initialized — skipping schema setup.")

        run_basic_tests()

        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
