Overview
- Conversation continuity is implemented with `conversations` and `messages` tables keyed by `channel='whatsapp'` and `external_user_id=<From>`.
- MCP tools are restricted to reservation/time operations with no PII access or return.
- System prompts include a timezone-aware `current_date` for correct relative date handling.

Env Vars
- `CONVERSATION_TTL_HOURS`: hours to reuse a conversation (default: `24`).
- `APP_TIMEZONE`: IANA timezone for date context (default: `America/Ciudad_Juarez`).
- `DATABASE_URL`: SQLAlchemy DSN for app models (e.g., `postgresql+psycopg2://user:pass@localhost:5433/maitred`).
- `MAITRED_DB`: psycopg DSN for `manage.py`/schema ops (e.g., `dbname=maitred user=postgres password=postgres host=localhost port=5433`).
- `SQLALCHEMY_CREATE_ALL`: if set to `1`, models auto-create tables; default is `0` to avoid accidental writes.

DB Migration
- Initialize or upgrade the schema:
  - `python manage.py --reset` (drops and recreates schema; development only)
  - or `python manage.py` (creates missing tables/columns)

Running Tests
- From repo root:
  - `python -m unittest discover -s tests -p "test_*.py" -v`

Manual Threading Test
- Start the app (e.g., with Uvicorn):
  - `uvicorn webapp:app --reload`
- Send two messages within TTL; they should thread in the same conversation:
  - `curl -X POST http://127.0.0.1:8000/message \
      -d 'From=whatsapp:+15551234567' \
      -d 'Body=Hello' \
      -d 'MessageSid=SM_TEST_1'`
  - `curl -X POST http://127.0.0.1:8000/message \
      -d 'From=whatsapp:+15551234567' \
      -d 'Body=Need a table' \
      -d 'MessageSid=SM_TEST_2'`
- Expected:
  - One row in `conversations` for that number; two inbound rows in `messages` linked to it.
  - Logs show a single `trace_id` per request with hashed phone numbers.

MCP Tools
- Exposed tools: `list_open_times(date_iso, party_size)`, `check_availability(date_iso, time_24h, party_size)`, `create_reservation(slot_id, party_size, client_ref?)`.
- Server resolves `client_ref` if present; tools never accept free-text PII.
- Responses include only opaque ids and times (no names/phones/emails).
Setup
- Copy `.env.example` to `.env` and fill in values. `.env` is gitignored.
- Prefer a single virtualenv (e.g., `.venv/`).
- Install dependencies with: `pip install -r requirements.txt` (uses `constraints.txt` for pinning).

