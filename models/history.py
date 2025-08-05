from typing import List, Tuple, Optional
from database.connection import connect

"""
CREATE TABLE IF NOT EXISTS History (
    history_id     SERIAL PRIMARY KEY,
    client_id      INTEGER NOT NULL,
    restaurant_id  INTEGER,
    employee_id      INTEGER,
    items_ordered  TEXT
    visit_date     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES Clients(client_id) ON DELETE CASCADE,
    FOREIGN KEY (restaurant_id) REFERENCES Restaurants(restaurant_id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES Employees(employee_id) ON DELETE SET NULL
);
"""

def get_client_history (client_id: int) -> list[Tuple]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                History.history_id,
                History.visit_date,
                Histoy.employee_id
                Notes.note_text,
                Notes.created_at
            FROM History
            LEFT JOIN Notes ON History.history_id = Notes.history_id
            WHERE History.client_id = %s
            ORDER BY History.visit_date DESC
        """(client_id,))    
    return cur.fetchall()

def add_visit(client_id: int, employee_id: int, items_ordered: str, note_text: Optional[str] = None):
    with connect() as conn:
        cur = conn.cursor()

        # Insert into History table
        cur.execute("""
            INSERT INTO History (client_id, employee_id, items_ordered)
            VALUES (%s, %s, %s)
            RETURNING history_id
        """, (client_id, employee_id, items_ordered))
        history_id = cur.fetchone()[0]

        # If note text is provided, insert into Notes table
        if note_text:
            cur.execute("""
                INSERT INTO Notes (client_id, history_id, employee_id, note_text)
                VALUES (%s, %s, %s, %s)
            """, (client_id, history_id, employee_id, note_text))

        conn.commit()