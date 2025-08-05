"""
Run `python -m database.schema` to (re)create tables & views.
"""
from .connection import connect

"""Some tables use CURRENT_TIMESTAMP, others use CURRENT_DATE. Consider consistency:
- fix later
"""

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS public;
SET search_path TO public;


CREATE TABLE IF NOT EXISTS Clients (
    client_id         SERIAL PRIMARY KEY,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    phone_number      TEXT UNIQUE NOT NULL,
    email             TEXT UNIQUE,
    client_summary    TEXT,
    ai_summary        TEXT,
    birthday          DATE,
    preferred_seating TEXT,
    preferred_server  TEXT,
    preferred_communication TEXT,
    last_visit        TIMESTAMP,
    allow_marketing   BOOLEAN DEFAULT TRUE CHECK (allow_marketing IN (TRUE, FALSE)),
    date_created      DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS Restaurants (
    restaurant_id SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    location      TEXT
);

CREATE TABLE IF NOT EXISTS Employees (
    employee_id  SERIAL PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('server', 'manager', 'owner')),
    access_code  INTEGER NOT NULL CHECK (access_code BETWEEN 1000 AND 9999),
    username     TEXT UNIQUE,
    password     TEXT
);

CREATE TABLE IF NOT EXISTS History (
    history_id     SERIAL PRIMARY KEY,
    client_id      INTEGER NOT NULL,
    restaurant_id  INTEGER,
    employee_id      INTEGER,
    items_ordered  TEXT,
    visit_date     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES Clients(client_id) ON DELETE CASCADE,
    FOREIGN KEY (restaurant_id) REFERENCES Restaurants(restaurant_id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES Employees(employee_id) ON DELETE SET NULL
);

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

def initialize_database():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(SCHEMA_SQL)

    conn.commit()
    conn.close()
    print("Database initialized")

if __name__ == "__main__":
    initialize_database()