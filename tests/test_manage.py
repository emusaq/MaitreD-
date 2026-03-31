import unittest
from unittest.mock import Mock, patch

import manage
from database.connection import connect


class ManageTests(unittest.TestCase):
    def test_raw_connection_uses_database_url_config(self):
        with (
            patch("database.connection.get_database_url", return_value="postgresql+psycopg2://user:pass@db.example:5433/maitred"),
            patch("database.connection.psycopg.connect") as psycopg_connect,
        ):
            connect()

        psycopg_connect.assert_called_once_with(
            "postgresql://user:pass@db.example:5433/maitred"
        )

    def test_up_to_date_path_still_seeds_reservation_settings(self):
        conn = Mock()

        with (
            patch("manage.sys.argv", ["manage.py"]),
            patch("manage.connect", return_value=conn),
            patch("manage.is_initialized", return_value=True),
            patch("manage.alembic_command.upgrade") as upgrade,
            patch("manage.seed_reservation_settings") as seed_settings,
            patch("manage.seed_test_employee") as seed_employee,
            patch("manage.run_basic_tests") as run_tests,
        ):
            manage.main()

        conn.close.assert_called_once()
        upgrade.assert_called_once()
        seed_settings.assert_called_once()
        seed_employee.assert_called_once()
        run_tests.assert_called_once()


if __name__ == "__main__":
    unittest.main()
