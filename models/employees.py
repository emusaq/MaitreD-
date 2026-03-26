from typing import List, Optional
import secrets
import bcrypt
from sqlalchemy.orm import Session

from models.models import SessionLocal, Employee


# --- Password helpers ---

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --- CRUD ---

def list_employees(db: Optional[Session] = None) -> List[Employee]:
    """Return a list of all employees."""
    if db is None:
        db = SessionLocal()
    return db.query(Employee).order_by(Employee.last_name).all()


def get_employee_by_id(employee_id: int, db: Optional[Session] = None) -> Optional[Employee]:
    """Return an employee by id."""
    if db is None:
        db = SessionLocal()
    return db.get(Employee, employee_id)


def get_employee_by_username(username: str, db: Optional[Session] = None) -> Optional[Employee]:
    """Return an employee by username."""
    if db is None:
        db = SessionLocal()
    return db.query(Employee).filter_by(username=username).first()


def get_employee_by_name(
    first_name: str, last_name: str, db: Optional[Session] = None
) -> Optional[Employee]:
    """Return an employee by first and last name."""
    if db is None:
        db = SessionLocal()
    return (
        db.query(Employee)
        .filter_by(first_name=first_name, last_name=last_name)
        .first()
    )


def update_employee_role(
    employee_id: int, role: str, db: Optional[Session] = None
) -> bool:
    """Update an employee's role."""
    if db is None:
        db = SessionLocal()
    employee = get_employee_by_id(employee_id, db)
    if employee:
        employee.role = role
        db.commit()
        return True
    return False


def delete_employee(employee_id: int, db: Optional[Session] = None) -> bool:
    """Delete the employee by id."""
    if db is None:
        db = SessionLocal()
    employee = get_employee_by_id(employee_id, db)
    if employee:
        db.delete(employee)
        db.commit()
        return True
    return False


def create_employee(
    first_name: str,
    last_name: str,
    role: str,
    password: str,
    access_code: Optional[int] = None,
    db: Optional[Session] = None,
) -> int:
    """Create a new employee with a hashed password. Returns employee_id."""
    if db is None:
        db = SessionLocal()
    if access_code is None:
        access_code = secrets.randbelow(9000) + 1000
    username = f"{first_name[0].lower()}{last_name.lower()}{access_code}"
    new_employee = Employee(
        first_name=first_name,
        last_name=last_name,
        role=role,
        access_code=access_code,
        username=username,
        password=hash_password(password),
    )
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)
    return new_employee.employee_id
