# CLAUDE.md — Agent Instructions for Maitred App

This file is the authoritative guide for any AI agent (Claude or otherwise) working on this codebase. Read it fully before writing any code.

---

## What This Project Is

**Maitred** is a WhatsApp-based restaurant reservation system for Garufa, a high-end Argentine restaurant. Guests text a WhatsApp number, an LLM (GPT-4o-mini) handles the conversation, and reservations are created in PostgreSQL via MCP tools. Front-of-house staff manage reservations through a web portal at `/staff/`.

---

## Architecture at a Glance

```
WhatsApp → Twilio → POST /message (webapp.py)
                         ↓
                   security.py (injection check, PII filter)
                   rate_limiter.py (per-phone sliding window)
                         ↓
                   OpenAI GPT-4o-mini
                         ↓
                   mcp/mcp_server.py (list_open_times, check_availability, create_reservation)
                         ↓
                   PostgreSQL via SQLAlchemy (models/models.py)

Staff browser → GET/POST /staff/* (staff/app.py)
                         ↓
                   Jinja2 templates (staff/templates/)
                         ↓
                   PostgreSQL (reservation_settings, reservations, clients)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `webapp.py` | FastAPI app entry point. Mounts staff router. Handles `/message` Twilio webhook. |
| `security.py` | Prompt injection detection, output PII filter, hardened system prompt builder. |
| `rate_limiter.py` | In-memory sliding-window rate limiter (per phone number). |
| `mcp/mcp_server.py` | MCP tools: `list_open_times`, `check_availability`, `create_reservation`. Reads `reservation_settings` from DB. |
| `models/models.py` | All SQLAlchemy ORM models + `get_db()` dependency + `SessionLocal`. |
| `models/client.py` | Client CRUD functions. |
| `models/employees.py` | Employee CRUD + `hash_password()` / `verify_password()` (bcrypt). |
| `models/restaurants.py` | Restaurant CRUD. |
| `models/history.py` | Visit history CRUD. |
| `models/notes.py` | Notes CRUD. |
| `database/schema.py` | Raw SQL `CREATE TABLE` statements used by `manage.py`. |
| `database/connection.py` | Raw psycopg connection used only by `manage.py` for schema init. |
| `manage.py` | CLI to initialize/reset DB schema and seed `reservation_settings`. |
| `utils.py` | Twilio `send_message()`, `logger`, `redact_pii()`, `new_trace_id()`. |
| `staff/app.py` | Staff webapp APIRouter: login, dashboard, reservations, settings, client profile. |
| `staff/auth.py` | Cookie-based session auth using `itsdangerous`. `get_current_employee()` FastAPI dependency. |
| `staff/templates/` | Jinja2 HTML templates. No build step required. |

---

## Database Tables

| Table | Description |
|-------|-------------|
| `conversations` | WhatsApp conversation threads (channel, external_user_id, TTL-managed). |
| `messages` | Individual messages per conversation (inbound/outbound, Twilio SID for idempotency). |
| `clients` | Guest records: name, phone, email, preferences, birthday, marketing flag. |
| `restaurants` | Restaurant records (name, location). |
| `employees` | Staff: role (`server`/`manager`/`owner`), bcrypt password, access_code, username. |
| `history` | Visit records linked to client/restaurant/employee. |
| `notes` | Staff notes per client or per visit. |
| `reservations` | Booking records: slot_id (e.g. `2025-01-15_19:00`), party_size, client_id. |
| `reservation_settings` | Staff-controlled config: enabled toggle, hours, slot interval, capacity limits. |

---

## Session Management Pattern

All model files (`models/`) use this pattern — not mutable defaults:

```python
def some_function(db: Optional[Session] = None):
    if db is None:
        db = SessionLocal()
    ...
```

FastAPI endpoints use `db: Session = Depends(get_db)` where `get_db` lives in `models/models.py`.

**Never use `db: Session = SessionLocal()` as a default parameter.** That creates a shared singleton.

---

## Security Rules

1. **Prompt injection**: `security.py:sanitize_input()` checks before forwarding to LLM. If flagged, return `INJECTION_REPLY` and stop. Do not add LLM calls anywhere that bypass this check.
2. **PII in LLM output**: Always pass LLM responses through `security.py:filter_output()` before sending to users.
3. **System prompt**: Always use `security.py:build_system_prompt()`. Do not write inline system prompts in `webapp.py`.
4. **MCP tools**: Tools must never accept names, emails, or phone numbers as parameters. Only opaque integer `client_ref`. Responses must never contain PII.
5. **Twilio webhook**: Verified via HMAC in `webapp.py`. Bypass only with `TWILIO_SKIP_VALIDATION=true` for local dev. Never disable in production.
6. **Staff routes**: All `/staff/*` routes except `/staff/login` require a valid signed cookie. `/staff/settings` requires `manager` or `owner` role. Enforced by `staff/auth.py:get_current_employee()` and `require_manager()`.
7. **Passwords**: Always hash with `models/employees.py:hash_password()` (bcrypt). Never store plaintext.

---

## Coding Conventions

- **Python 3.11+**. Use `datetime`, `zoneinfo`, `match` where appropriate.
- **FastAPI** for all HTTP. No Flask, no Django.
- **SQLAlchemy ORM** for all data access. Raw SQL only in `manage.py` schema init and MCP tool queries (using `text()` with parameterized binds — never f-strings in SQL).
- **Jinja2** for staff templates. No React, no npm, no build steps.
- **`python-decouple`** for all config (`config("KEY", default=...)`). No `os.environ.get()` for app config.
- Type hints on all function signatures. `Optional[X]` not `X | None` for Python <3.10 compatibility.
- No docstrings on trivial functions. Add comments only where logic is non-obvious.

---

## What NOT to Do

- Do not add new raw psycopg connections outside `database/connection.py`. Use SQLAlchemy.
- Do not add a second schema definition. `database/schema.py` is the raw SQL source; `models/models.py` is the ORM source. They must stay in sync manually until Alembic is added.
- Do not import `app` or `get_db` from `webapp.py` in other modules. `get_db` lives in `models/models.py`.
- Do not add frontend frameworks (React, Vue, etc.) without explicit instruction.
- Do not commit `.env`. It is gitignored. Use `.env.example` for documentation.
- Do not add `pyngrok` usage to new code — it is legacy for local tunneling only.

---

## Environment Variables

See `.env.example` for the full list. Critical ones:

| Variable | Used In | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `models/models.py` | Full SQLAlchemy URL. Takes priority over DB_USER/DB_PASSWORD. |
| `OPENAI_API_KEY` | `webapp.py` | Tolerates missing key at import time (tests). |
| `TWILIO_AUTH_TOKEN` | `webapp.py` | Required for webhook verification in production. |
| `SECRET_KEY` | `staff/auth.py` | Signs session cookies. Must be random and kept secret. |
| `TWILIO_SKIP_VALIDATION` | `webapp.py` | Set `true` for local dev only. Never in production. |

---

## Working with This Project

### Before starting any task
1. Read `updates.md` to understand the latest state of the project.
2. Read the files you plan to modify before editing them.
3. Check `dev.md` for the current problem list.

### After completing any task
1. Update `updates.md` with what changed and why.
2. Update `dev.md` if new problems were introduced or resolved.

### Running tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### Adding a new model
1. Add the ORM class to `models/models.py`.
2. Add the raw `CREATE TABLE` to `database/schema.py`.
3. Run `python manage.py --reset` on a dev database to verify both stay in sync.
4. Create a `models/<table>.py` CRUD file following the pattern in `models/client.py`.
