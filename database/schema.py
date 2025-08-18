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

-- Base conversations table (upgrade to durable conversation store)
CREATE TABLE IF NOT EXISTS conversations (
    id               SERIAL PRIMARY KEY,
    -- New conversation routing fields
    channel          TEXT,
    external_user_id TEXT,
    opened_at        TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status           TEXT DEFAULT 'open'
);

-- Helpful index to look up by channel + external_user_id
CREATE INDEX IF NOT EXISTS idx_conversations_channel_user
    ON conversations (channel, external_user_id);

-- Backward-compat: if an old conversations table exists with legacy columns,
-- ensure new columns are present (no-op if already added above on fresh DB)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='channel'
    ) THEN
        ALTER TABLE conversations ADD COLUMN channel TEXT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='external_user_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN external_user_id TEXT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='opened_at'
    ) THEN
        ALTER TABLE conversations ADD COLUMN opened_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='updated_at'
    ) THEN
        ALTER TABLE conversations ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='status'
    ) THEN
        ALTER TABLE conversations ADD COLUMN status TEXT DEFAULT 'open';
    END IF;
END $$;

-- Messages table with idempotency via external_message_id (e.g., Twilio MessageSid)
CREATE TABLE IF NOT EXISTS messages (
    id                   SERIAL PRIMARY KEY,
    conversation_id      INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction            TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
    text                 TEXT NOT NULL,
    external_message_id  TEXT,
    created_at           TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_external_id
    ON messages (external_message_id)
    WHERE external_message_id IS NOT NULL;


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

-- Minimal reservations table and unique slot identifier to support MCP tools
CREATE TABLE IF NOT EXISTS reservations (
    id           SERIAL PRIMARY KEY,
    date_iso     DATE NOT NULL,
    time_24h     TIME NOT NULL,
    party_size   INTEGER NOT NULL CHECK (party_size > 0),
    slot_id      TEXT NOT NULL UNIQUE,
    client_id    INTEGER REFERENCES Clients(client_id),
    note         TEXT,
    note-author  TEXT
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
