from typing import List, Tuple, Optional
from database.connection import connect

"""
CREATE TABLE IF NOT EXISTS Clients (
    client_id         SERIAL PRIMARY KEY,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    phone_number      TEXT UNIQUE NOT NULL,
    email             TEXT UNIQUE,
    client_summary    TEXT,
    birthday          DATE,
    preferred_seating TEXT,
    preferred_server  TEXT,
    last_visit        TIMESTAMP,
    allow_marketing   BOOLEAN DEFAULT TRUE CHECK (allow_marketing IN (TRUE, FALSE)),
    date_created      DATE DEFAULT CURRENT_DATE
);
"""


def list_clients() -> List[Tuple]:
    # return a list of all clients
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT client_id, first_name, last_name, phone_number
            FROM Clients
            ORDER BY last_name, first_name
        """)
        return cur.fetchall()
    
def get_client_by_id(client_id_in: int) -> Optional[Tuple]:
    # return client by id
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Clients WHERE client_id = %s", (client_id_in,))
        return cur.fetchone()
    
def get_client_by_name(first_name: str, last_name: str) -> Optional[Tuple]:
    # return a client row by first and last name 
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM Clients
            WHERE first_name = %s AND last_name = %s
        """, (first_name, last_name))
        return cur.fetchone()
    
def get_client_by_phone(phone_number: str) -> Optional[Tuple]:
    # return client row by phone number
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Clients WHERE phone_number = %s", (phone_number,))
        return cur.fetchone()

def create_client(
        first_name: str,
        last_name: str,
        phone_number: str,
        email: Optional[str] = None,
        birthday: Optional[str] = None,
        preferred_seating: Optional[str] = None,
        preferred_server: Optional[str] = None,
        allow_marketing: bool = True
) -> int:
    # create a client and return their client_id
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Clients (
                first_name, last_name, phone_number,
                email, birthday, preferred_seating,
                preferred_server, allow_marketing   
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING client_id
        """, (
            first_name, last_name, phone_number, 
            email, birthday, preferred_seating, preferred_server,
            allow_marketing
        ))
        client_id = cur.fetchone()[0]
        conn.commit()
        return client_id
    
def update_client_summary(client_id: int, summary: str) -> bool:
    # updates the summary note for a client.
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE Clients
            SET client_summary = %s
            WHERE client_id = %s
        """, (summary, client_id))
        conn.commit()
        return cur.rowcount > 0
    
def update_last_visit(client_id: int) -> bool:
    # updates the last visit
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE Clients
            SET last_visit = CURRENT_TIMESTAMP
            WHERE client_id = %s
        """, (client_id,))
        conn.commit()
        return cur.rowcount > 0


def get_or_create_client_id(full_name: str) -> int:
    """Retrieve a client_id for ``full_name`` or create a placeholder client."""
    parts = full_name.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    existing = get_client_by_name(first_name, last_name)
    if existing:
        return existing[0]

    # Create a placeholder client with an unknown phone number
    placeholder_phone = "unknown"
    return create_client(first_name, last_name, placeholder_phone)
    
