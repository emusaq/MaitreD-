# dev.md — Developer Reference

Last updated: 2026-03-26

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env        # fill in all values

# 3. Initialize the database
python manage.py

# 4. Create a staff account
python -c "from models.employees import create_employee; create_employee('Ana', 'Lopez', 'manager', 'yourpassword')"

# 5. Start the server
python run.py start
```

The server runs startup checks on all connections before starting. If anything fails, it will tell you exactly what is wrong before touching the process.

```bash
python run.py reload        # restart (picks up code changes, re-runs all checks)
python run.py quit          # stop the server
```

Logs are written to `/tmp/maitred.log`. To follow them live:
```bash
tail -f /tmp/maitred.log
```

---

## How to Run Everything

### Prerequisites
- Python 3.11+
- PostgreSQL running on `localhost:5433` (or set `DATABASE_URL`)
- A Twilio account with a WhatsApp-enabled number
- An OpenAI API key

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in all values:
```bash
cp .env.example .env
```

Minimum required for local dev:
```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/maitred
OPENAI_API_KEY=sk-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_NUMBER=+1...
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
TWILIO_SKIP_VALIDATION=true
```

### 3. Initialize the database
```bash
python manage.py
```
First run creates all tables and seeds a default `reservation_settings` row.

To wipe and rebuild from scratch:
```bash
python manage.py --reset
```

### 4. Create a staff account
Default Login for devs
admin, admin

Drop into Python and call directly:
```python
from models.employees import create_employee
create_employee("Ana", "Lopez", "manager", "yourpassword")
```
This hashes the password automatically and prints the `employee_id`.

### 5. Start the server
```bash
python run.py start
```

Runs health checks on all connections first, then starts uvicorn in the background.

- **Staff portal:** http://localhost:8000/staff/login
- **Health check:** http://localhost:8000/
- **Twilio webhook endpoint:** http://localhost:8000/message (POST)

### 6. Expose to Twilio (local dev)
Twilio needs a public HTTPS URL. Use ngrok:
```bash
ngrok http 8000
```
Copy the HTTPS forwarding URL and set it as your Twilio WhatsApp webhook:
- Twilio Console → Messaging → Try it out → Send a WhatsApp message → Sandbox settings
- Set "When a message comes in" to: `https://<your-ngrok>.ngrok-free.app/message`
- Method: POST

### 7. Run tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Database

### Connection
- **ORM (application code):** via `models/models.py:SessionLocal` and `get_db()` — uses `DATABASE_URL` env var
- **Raw psycopg (manage.py only):** via `database/connection.py:connect()` — uses `MAITRED_DB` env var or defaults to `localhost:5433`
- **Default dev port:** 5433 (non-standard — check your local Postgres config)

### Schema management
- Tables are defined in two places (known tech debt):
  - `database/schema.py` — raw SQL, used by `manage.py`
  - `models/models.py` — SQLAlchemy ORM, used by the app
- Both must be kept in sync manually
- No Alembic migrations yet (planned)

### Useful psql commands
```sql
-- List all tables
\dt

-- Check reservation settings
SELECT * FROM reservation_settings;

-- Today's reservations
SELECT * FROM reservations WHERE date_iso = CURRENT_DATE;

-- View conversations
SELECT id, channel, external_user_id, status, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 20;
```

---

## Twilio

### Webhook
- Endpoint: `POST /message`
- Twilio sends form data: `From` (e.g. `whatsapp:+521234567890`), `Body`, `MessageSid`
- Webhook signature is verified via HMAC using `TWILIO_AUTH_TOKEN`
- Set `TWILIO_SKIP_VALIDATION=true` in local dev to bypass signature check

### Sending messages
- Handled by `utils.py:send_message(to, body)`
- Uses `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_NUMBER` from env
- Returns Twilio MessageSid on success, `None` on failure (non-fatal)

### Test a WhatsApp message locally
1. Start server + ngrok
2. Set ngrok URL in Twilio sandbox
3. Send "join <sandbox-keyword>" from your WhatsApp number to the Twilio sandbox number
4. Send any message — it will hit `/message`

---

## OpenAI

- Model: `gpt-4o-mini`
- Used in: `webapp.py` `/message` endpoint
- System prompt is built by `security.py:build_system_prompt(current_date)`
- Context window: last 20 messages from the conversation
- `max_tokens=200`, `temperature=0.5`
- If `OPENAI_API_KEY` is missing at startup, the app runs but `/message` will fail gracefully

---

## MCP Server

- File: `mcp/mcp_server.py`
- Mounts on the FastAPI `app` object from `webapp.py`
- Three tools: `list_open_times`, `check_availability`, `create_reservation`
- All tools read `reservation_settings` from DB for hours/capacity/enabled state
- Tool responses never contain PII — only opaque IDs and times

---

## Staff Webapp

- Routes: `/staff/login`, `/staff/`, `/staff/reservations`, `/staff/settings`, `/staff/clients/{id}`
- Auth: cookie-based signed sessions (8-hour TTL), managed by `staff/auth.py`
- Templates: server-rendered Jinja2 in `staff/templates/` — no build step
- Roles: `server` can view; `manager` and `owner` can access settings

---

## Security Layers

| Layer | File | What it does |
|-------|------|-------------|
| Twilio sig verify | `webapp.py` | Rejects unsigned webhook requests (403) |
| Rate limiting | `rate_limiter.py` | 10 msgs/60s per phone; returns 429 + WhatsApp message |
| Injection detection | `security.py` | Regex patterns on inbound text; drops to canned response if flagged |
| Hardened prompt | `security.py` | System prompt explicitly forbids role changes, PII reveal |
| Output PII filter | `security.py` | Scrubs phone/email/ID patterns from LLM response before sending |
| Staff auth | `staff/auth.py` | Signed cookie required for all `/staff/*` except login |

---

## Current Problems

### High priority
0. **Staff portal can fail on legacy DB schema** — Staff routes now assume newer `reservations` and `reservation_settings` columns exist. Older databases missing these columns will break `/staff/`, `/staff/reservations`, or confirm/deny/cancel flows. Regression coverage added in `tests/test_db_schema_consistency.py`, but deployed DBs still need verification.
1. **Dual schema sources** — `database/schema.py` (raw SQL) and `models/models.py` (ORM) can silently diverge. No Alembic. Any schema change must be made in both places manually.
2. **No Alembic migrations** — schema changes require `manage.py --reset` (data loss) or manual `ALTER TABLE`. This is not viable for production data.
3. **In-memory rate limiter** — `rate_limiter.py` uses a Python dict. Restarting the server resets all windows. Not suitable for multi-process or multi-instance deployments.
4. **Existing plaintext passwords** — `create_employee()` now hashes, but any employees created before this change have plaintext passwords in the DB. They must be reset.
5. **Overbooking under multi-process deployment** — The conditional INSERT in `reservation_tools.py` and `mcp/mcp_server.py` closes the race for a single uvicorn worker. Running multiple workers (e.g. `--workers 4`) re-opens the race. Fix requires `pg_advisory_xact_lock` or `SERIALIZABLE` isolation before scaling to multiple workers.

### Medium priority
6. **Restaurant hours not per-restaurant** — `reservation_settings` has a `restaurant_id` FK but it is not used. `mcp_server.py` always reads the first row. Multi-restaurant support is not implemented.
7. **Pydantic v1 `@validator` deprecation** — `mcp/mcp_server.py` uses the deprecated `@validator` decorator. Should be migrated to `@field_validator` (Pydantic v2).
8. **No error monitoring** — No Sentry or equivalent. Errors only surface in server logs.
9. **No HTTPS enforcement** — Staff session cookies are set with `secure=False`. Must be `True` in production (requires HTTPS).
10. **`psycopg` still in constraints.txt** — Was removed from `requirements.txt` but may still be in `constraints.txt`. Only `psycopg2-binary` is needed.

### Low priority
11. **Missing FK indexes** — `history.client_id` and `notes.history_id` lack indexes. Query performance will degrade at scale.
12. **Inconsistent table casing in schema** — `schema.py` uses `Clients`, `Restaurants`, `Employees`, `History`, `Notes` (capitalized) but PostgreSQL lowercases them. ORM models use lowercase. Works in practice but is confusing.
13. **`manage.py --reset` is destructive** — Drops the entire schema. Should warn more prominently and/or require `--confirm` for production use.
14. **No blackout dates** — No way to block specific dates from accepting reservations (e.g. private events, holidays).
15. **No data retention policy** — Messages and conversations accumulate indefinitely. No cleanup job.

---

## Suggested Next Changes

### Immediate (before wider beta use)
- [x] Add Alembic for schema migrations — **DONE 2026-03-30**
- [x] Rotate Twilio + OpenAI credentials (previously committed to git) — **DONE 2026-03-30**
- [x] Migrate to WhatsApp Business API (Option A: Twilio WhatsApp Business sender; template support added) — **DONE 2026-03-30** — still need to register templates in Meta/Twilio console and set `TWILIO_*_TEMPLATE_SID` env vars
- [x] Move rate limiter to Redis for multi-process safety — **DONE 2026-03-30**
- [x] Set `secure=True` on session cookie via `SECURE_COOKIES` env var — **DONE 2026-03-30**
- [ ] Remove unused `StaticFiles` import from `webapp.py`
- [ ] Force-reset passwords for any employees seeded before bcrypt was added
- [ ] Remove `psycopg` from `constraints.txt` (standardize on `psycopg2-binary`)

### Short-term
- [x] Migrate Pydantic `@validator` to `@field_validator` in `mcp/mcp_server.py` — **DONE 2026-03-30**
- [x] Add `--confirm` flag to `manage.py --reset` — **DONE 2026-03-30**
- [x] Add FK indexes to `history.client_id` and `notes.history_id` — **DONE 2026-03-30**
- [ ] Add Sentry error monitoring (`sentry-sdk[fastapi]`)
- [ ] Per-restaurant reservation settings (use `restaurant_id` filter in MCP tools)
- [ ] Blackout dates table + UI in staff settings

### Longer-term
- [ ] Replace MCP reservation tools with OpenAI function-calling (native tool use, cleaner integration)
- [ ] Conversation summary/archiving job (prevent unbounded message growth)
- [ ] AI-generated `ai_summary` on client records after each visit
- [ ] Staff notifications (e.g. Slack or email when reservation is created)
- [ ] Export reservations to CSV from staff portal

---

## Project File Tree

```
Maitred App/
├── webapp.py                  # FastAPI app + /message webhook
├── security.py                # Injection detection, PII filter, system prompt
├── rate_limiter.py            # Sliding window rate limiter
├── utils.py                   # Twilio send, logger, PII redaction
├── manage.py                  # DB init/reset CLI
├── requirements.txt
├── constraints.txt
├── Dockerfile
├── Procfile
├── .env.example
├── .gitignore
├── CLAUDE.md                  # AI agent instructions
├── dev.md                     # This file
├── updates.md                 # Task changelog / working memory
│
├── models/
│   ├── models.py              # All ORM models + get_db()
│   ├── client.py              # Client CRUD
│   ├── employees.py           # Employee CRUD + bcrypt helpers
│   ├── restaurants.py         # Restaurant CRUD
│   ├── history.py             # Visit history CRUD
│   └── notes.py               # Notes CRUD
│
├── database/
│   ├── __init__.py
│   ├── connection.py          # Raw psycopg (manage.py only)
│   ├── schema.py              # Raw SQL CREATE TABLE statements
│   └── test_connection.py     # Quick connection test
│
├── mcp/
│   ├── __init__.py
│   └── mcp_server.py          # MCP tools for reservation flow
│
├── staff/
│   ├── __init__.py
│   ├── app.py                 # Staff webapp routes
│   ├── auth.py                # Session auth
│   └── templates/
│       ├── base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── reservations.html
│       ├── settings.html
│       └── client.html
│
├── api/
│   └── routes/
│       └── __init__.py        # Empty, reserved for future REST API
│
└── tests/
    ├── test_conversations.py
    ├── test_e2e_whatsapp.py
    └── test_mcp_tools.py
```
