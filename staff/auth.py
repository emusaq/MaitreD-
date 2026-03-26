"""Session-based auth for the staff webapp."""
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from decouple import config

from models.employees import get_employee_by_username, verify_password
from models.models import Employee, SessionLocal

_SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")
_serializer = URLSafeTimedSerializer(_SECRET_KEY)
_COOKIE_NAME = "maitred_session"
_SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours


def create_session_cookie(employee_id: int, role: str) -> str:
    return _serializer.dumps({"id": employee_id, "role": role})


def decode_session_cookie(token: str) -> Optional[dict]:
    try:
        return _serializer.loads(token, max_age=_SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def authenticate(username: str, password: str) -> Optional[Employee]:
    """Return the Employee if credentials are valid, else None."""
    db = SessionLocal()
    try:
        employee = get_employee_by_username(username, db)
        if employee and verify_password(password, employee.password):
            return employee
        return None
    finally:
        db.close()


def get_current_employee(request: Request) -> dict:
    """Dependency: return session payload or raise 302 redirect to login."""
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/staff/login"})
    payload = decode_session_cookie(token)
    if payload is None:
        raise HTTPException(status_code=302, headers={"Location": "/staff/login"})
    return payload


def require_manager(session: dict = None) -> dict:
    """Raise 403 if employee is not manager or owner."""
    if session and session.get("role") not in ("manager", "owner"):
        raise HTTPException(status_code=403, detail="Manager or owner access required.")
    return session


COOKIE_NAME = _COOKIE_NAME
