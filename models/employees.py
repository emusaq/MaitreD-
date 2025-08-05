from typing import List, Optional
import secrets
from sqlalchemy.orm import Session

from models.models import SessionLocal, Employee


def list_employees(db: Session = SessionLocal()) -> List[Employee]:
    """Return a list of all employees."""
    return db.query(Employee).order_by(Employee.last_name).all()


def get_employee_by_id(employee_id: int, db: Session = SessionLocal()) -> Optional[Employee]:
    """Return an employee by id."""
    return db.get(Employee, employee_id)


def get_employee_by_name(
    first_name: str, last_name: str, db: Session = SessionLocal()
) -> Optional[Employee]:
    """Return an employee by first and last name."""
    return (
        db.query(Employee)
        .filter_by(first_name=first_name, last_name=last_name)
        .first()
    )


def update_employee_role(
    employee_id: int, role: str, db: Session = SessionLocal()
) -> bool:
    """Update an employee's role."""
    employee = get_employee_by_id(employee_id, db)
    if employee:
        employee.role = role
        db.commit()
        return True
    return False


def delete_employee(employee_id: int, db: Session = SessionLocal()) -> bool:
    """Delete the employee by id."""
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
    db: Session = SessionLocal()
) -> int:
    """Create a new employee and return their employee_id."""
    if access_code is None:
        access_code = secrets.randbelow(9000) + 1000
    username = f"{first_name[0].lower()}{last_name.lower()}{access_code}"
    new_employee = Employee(
        first_name=first_name,
        last_name=last_name,
        role=role,
        access_code=access_code,
        username=username,
        password=password
    )
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)
    return new_employee.employee_id
