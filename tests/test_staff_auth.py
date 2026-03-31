import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["SQLALCHEMY_CREATE_ALL"] = "0"

import webapp
import staff.auth as auth
import staff.app as staff_app
from models.models import Base, Employee, get_db
from models.employees import hash_password, verify_password


class StaffAuthTests(unittest.TestCase):
    def setUp(self):
        db_path = "./test_staff_auth.db"
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass

        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._original_session_local = auth.SessionLocal
        self._original_secure_cookies = staff_app._secure_cookies
        auth.SessionLocal = self.SessionLocal

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        webapp.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(webapp.app)

    def tearDown(self):
        auth.SessionLocal = self._original_session_local
        staff_app._secure_cookies = self._original_secure_cookies
        webapp.app.dependency_overrides.clear()

    def test_login_with_missing_password_hash_returns_invalid_credentials(self):
        db = self.SessionLocal()
        db.add(Employee(
            first_name="Legacy",
            last_name="MissingHash",
            role="owner",
            access_code=1111,
            username="legacy-missing",
            password=None,
        ))
        db.commit()
        db.close()

        response = self.client.post(
            "/staff/login",
            data={"username": "legacy-missing", "password": "admin"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid username or password.", response.text)

    def test_login_with_plaintext_legacy_password_migrates_and_redirects(self):
        db = self.SessionLocal()
        db.add(Employee(
            first_name="Legacy",
            last_name="Plaintext",
            role="owner",
            access_code=1112,
            username="legacy-plain",
            password="admin",
        ))
        db.commit()
        db.close()

        response = self.client.post(
            "/staff/login",
            data={"username": "legacy-plain", "password": "admin"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/staff/")

        db = self.SessionLocal()
        employee = db.query(Employee).filter_by(username="legacy-plain").first()
        self.assertIsNotNone(employee)
        self.assertNotEqual(employee.password, "admin")
        self.assertTrue(verify_password("admin", employee.password))
        db.close()

    def test_login_with_valid_hash_redirects_to_dashboard(self):
        db = self.SessionLocal()
        db.add(Employee(
            first_name="Admin",
            last_name="User",
            role="owner",
            access_code=1113,
            username="admin",
            password=hash_password("admin"),
        ))
        db.commit()
        db.close()

        response = self.client.post(
            "/staff/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/staff/")

    def test_dashboard_loads_after_login(self):
        db = self.SessionLocal()
        db.add(Employee(
            first_name="Admin",
            last_name="User",
            role="owner",
            access_code=1114,
            username="admin",
            password=hash_password("admin"),
        ))
        db.commit()
        db.close()

        response = self.client.post(
            "/staff/login",
            data={"username": "admin", "password": "admin"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Today's Reservations", response.text)

    def test_login_cookie_is_not_marked_secure_over_http(self):
        staff_app._secure_cookies = True

        db = self.SessionLocal()
        db.add(Employee(
            first_name="Admin",
            last_name="User",
            role="owner",
            access_code=1115,
            username="admin",
            password=hash_password("admin"),
        ))
        db.commit()
        db.close()

        response = self.client.post(
            "/staff/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertNotIn("Secure", response.headers.get("set-cookie", ""))

    def test_login_cookie_is_marked_secure_over_https(self):
        staff_app._secure_cookies = True
        secure_client = TestClient(webapp.app, base_url="https://testserver")

        db = self.SessionLocal()
        db.add(Employee(
            first_name="Admin",
            last_name="User",
            role="owner",
            access_code=1116,
            username="admin",
            password=hash_password("admin"),
        ))
        db.commit()
        db.close()

        response = secure_client.post(
            "/staff/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("Secure", response.headers.get("set-cookie", ""))


if __name__ == "__main__":
    unittest.main()
