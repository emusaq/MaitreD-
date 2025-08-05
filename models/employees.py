from typing import List, Tuple, Optional
from database.connection import connect

"""
Employee model - CRUD helpers for the Employees table.
"""

#employee schema 
"""
CREATE TABLE IF NOT EXISTS Employees (
    employee_id  SERIAL PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('server', 'manager', 'owner')),
    access_code  INTEGER NOT NULL CHECK (access_code BETWEEN 1000 AND 9999),
    username     TEXT UNIQUE,
    password     TEXT
);
"""

def list_employees() -> List[Tuple]:
    # Return a list of all employees
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT employee_id,
                   first_name,
                   last_name,
                   role,
                   access_code,
                   username
            FROM Employees
            ORDER BY last_name
        """)
        return cur.fetchall()

def get_employee_by_id(employee_id) -> Optional[Tuple]:
    # return a list of all employees
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM Employees
            WHERE employee_id = %s
        """, (employee_id,))
        return cur.fetchone()

def get_employee_by_name(employee_first_name, employee_last_name) -> Optional[tuple]:
     # return an employee by name
     with connect() as conn:
         cur = conn.cursor()
         cur.execute("""
            SELECT * FROM Employees 
            WHERE first_name = %s AND last_name = %s
        """,(employee_first_name, employee_last_name))
         return cur.fetchone()


# Update an employee's role based on an integer code (1=server, 2=manager, 3=owner)
def update_employee_role(employee_id: int, role_code: int) -> None:
    role_map = {
        1: 'server',
        2: 'manager',
        3: 'owner'
    }
    if role_code not in role_map:
        raise ValueError("Invalid role code. Must be 1 (server), 2 (manager), or 3 (owner).")
    new_role = role_map[role_code]

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE Employees
            SET role = %s
            WHERE employee_id = %s
        """, (new_role, employee_id))
        conn.commit()

def delete_employee(employee_id) -> bool:
    # delete the employee by id
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM Employees WHERE employee_id = %s", (employee_id,))
        conn.commit()
        return cur.rowcount > 0
    
def create_employee(
        first_name: str,
        last_name: str,
        role: int,
        password: str,
) -> int:
    import secrets  # cryptographically secure random numbers
    role_map = {1: 'server', 2: 'manager', 3: 'owner'}
    # TODO: consider hashing/storing passwords securely (e.g., bcrypt)
    access_code = secrets.randbelow(9000) + 1000  # range 1000–9999
    
    if role not in role_map:
        raise ValueError("Invalid role code. Must be 1, 2, 3")

    username = f"{first_name[0].lower()}{last_name.lower()}{access_code}"
    role_text = role_map[role]

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Employees (first_name, last_name, role, access_code, username, password)
            VALUES (%s, %s, %s, %s, %s, %s)
            returning employee_id
        """,(first_name, last_name, role_text, access_code, username, password))
        employee_id = cur.fetchone()[0]
        conn.commit()
        return employee_id