import argparse
from contextlib import closing
from database.connection import connect
from database.schema import initialize_database
from fastapi import FastAPI
from sqlalchemy.orm import Session
from models.models import SessionLocal

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# .venv/bin/python main.py --reset
# wipe schema and rebuild (useful after schema changes)

# .venv/bin/python main.py
# normal startup (initialize only if needed)

#to activate venv
#source path/to/venv/bin/activate
#/Users/emiliomunoz/Desktop/APPS/MaitreDRevised/.venv/bin/activate

#to deactivate
#

def is_initialized(conn) -> bool:
    """
    Check whether the core schema already exists.
    We simply look for the 'clients' table in the public schema.
    """
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT to_regclass('public.clients');")
        return cur.fetchone()[0] is not None


def run_basic_tests() -> None:
    """
    Lightweight, repeatable test-runner.
    Each test is a tuple: (description, callable).  
    Add new tuples to the `tests` list for quick expansion.
    """
    print("\n🏃 Running basic sanity tests …")
    tests = []

    # --- Example placeholder tests -------------------------------
    import importlib
    tests.append((
        "models.client module import",
        lambda: importlib.import_module("models.client")
    ))
    # -------------------------------------------------------------

    passed, failed = 0, 0
    for desc, fn in tests:
        try:
            fn()
            print(f"✅ {desc}")
            passed += 1
        except Exception as exc:
            print(f"❌ {desc}: {exc}")
            failed += 1

    print(f"\nTests finished — {passed} passed, {failed} failed.\n")

def wipe_schema(conn) -> None:
    """
    Drop and recreate the public schema.  
    Useful when the schema changes during development/testing.
    """
    with closing(conn.cursor()) as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
        cur.execute("CREATE SCHEMA public;")
        cur.execute("GRANT ALL ON SCHEMA public TO public;")
    conn.commit()
    print("🗑️  Existing schema dropped and public schema recreated.")

def main():
    # --- parse CLI arguments ------------------------------------
    parser = argparse.ArgumentParser(
        description="Initialize, reset, and test the MaitreD database."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing schema and re‑initialize.",
    )
    args = parser.parse_args()
    # ------------------------------------------------------------

    try:
        # Connect to the DB
        conn = connect()
        print("✅ Database connection successful.")

        if args.reset:
            wipe_schema(conn)
            initialize_database()
            print("✅ Database reset & re‑initialized.")
        else:
            if not is_initialized(conn):
                initialize_database()
                print("✅ Database initialized successfully.")
            else:
                print("ℹ️  Database already initialized — skipping schema setup.")

        # Run quick model sanity tests
        run_basic_tests()

        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
import argparse
from contextlib import closing
from database.connection import connect
from database.schema import initialize_database
from models.models import SessionLocal
import importlib

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

def run_basic_tests() -> None:
    """Run lightweight sanity tests (e.g., module import tests)."""
    print("\n🏃 Running basic sanity tests …")
    tests = [
        ("SQLAlchemy module import test (models.client)",
         lambda: importlib.import_module("models.client"))
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
    parser = argparse.ArgumentParser(description="Initialize, reset, and test the MaitreD database.")
    parser.add_argument("--reset", action="store_true", help="Wipe existing schema and re‑initialize.")
    args = parser.parse_args()

    try:
        # Obtain a raw connection for executing raw SQL
        raw_conn = connect()
        print("✅ Raw database connection successful.")

        if args.reset:
            wipe_schema(raw_conn)
            initialize_database()
            print("✅ Database reset & re‑initialized.")
        else:
            if not is_initialized(raw_conn):
                initialize_database()
                print("✅ Database initialized successfully.")
            else:
                print("ℹ️  Database already initialized — skipping schema setup.")

        # Test SQLAlchemy integration by creating a session
        session = SessionLocal()
        print("✅ SQLAlchemy session created successfully.")
        session.close()

        run_basic_tests()

        raw_conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
