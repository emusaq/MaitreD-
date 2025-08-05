from typing import List, Tuple, Optional
from database.connection import connect

"""
CREATE TABLE IF NOT EXISTS Notes (
    note_id     SERIAL PRIMARY KEY,
    client_id   INTEGER NOT NULL,
    history_id  INTEGER,
    employee_id   INTEGER,
    note_text   TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES Clients(client_id) ON DELETE CASCADE,
    FOREIGN KEY (history_id) REFERENCES History(history_id),
    FOREIGN KEY (employee_id) REFERENCES Employees(employee_id) ON DELETE SET NULL
);
"""

# -----------------------------#
# CRUD operations for Notes    #
# -----------------------------#

def add_note(
    client_id: int,
    note_text: str,
    history_id: Optional[int] = None,
    employee_id: Optional[int] = None,
) -> int:
    """
    Create a new note. Returns the newly created note_id.
    """
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Notes (client_id, history_id, employee_id, note_text)
            VALUES (%s, %s, %s, %s)
            RETURNING note_id
            """,
            (client_id, history_id, employee_id, note_text),
        )
        note_id = cur.fetchone()[0]
        conn.commit()
        return note_id


def get_note(note_id: int) -> Optional[Tuple]:
    """Retrieve a single note by its primary key."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Notes WHERE note_id = %s", (note_id,))
        return cur.fetchone()


def get_notes_by_client(client_id: int) -> List[Tuple]:
    """Return every note that belongs to a given client."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM Notes WHERE client_id = %s ORDER BY created_at DESC",
            (client_id,),
        )
        return cur.fetchall()


def get_notes_by_history(history_id: int) -> List[Tuple]:
    """Return every note attached to a specific visit (history record)."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM Notes WHERE history_id = %s ORDER BY created_at DESC",
            (history_id,),
        )
        return cur.fetchall()


def update_note(note_id: int, new_text: str) -> None:
    """Update the body of an existing note."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE Notes
            SET note_text = %s,
                created_at = CURRENT_TIMESTAMP
            WHERE note_id = %s
            """,
            (new_text, note_id),
        )
        conn.commit()


def delete_note(note_id: int) -> None:
    """Remove a note permanently."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM Notes WHERE note_id = %s", (note_id,))
        conn.commit()
