# updates.md — Working Memory & Task Log

This file is updated after every significant task. It is the authoritative record of what has changed, why, and what is currently in progress. AI agents and developers should read this before starting work.

---

## Current State (2026-03-26)

**Status:** Pre-beta. Core WhatsApp → LLM → reservation flow is working. Staff portal is built. Security hardening is in place. Not yet deployed to production.

**Next action required:**
- Add Alembic for schema migrations
- Rotate credentials (Twilio, OpenAI) — current `.env` was previously committed to git
- Create at least one manager-role employee via `create_employee()` before demo

---

## Task Log

---

### 2026-03-26 — Reliability hardening (Phases 1–5)

**What changed:**

**`webapp.py`:**
- Removed unused `StaticFiles` import.
- Added `IntegrityError` import from `sqlalchemy.exc`.
- Inbound message flush now catches `IntegrityError` — handles the rare concurrent duplicate-SID race that could slip past the pre-read idempotency check.
- Conversation history query changed from `order_by(asc).limit()` to `order_by(desc).limit() + reverse()` so the LLM always receives the most recent `_history_limit` messages, not the oldest.
- Outbound commit tracked with `outbound_persisted` flag; SID back-fill only attempted when the row was successfully committed, preventing a `None.id` reference on DB failure.

**`reservation_tools.py`:**
- Added `_validate_slot_id(slot_id, settings)` — checks format (regex), valid date/time components, slot within configured business hours, and alignment to slot interval. Returns an error string or `None`.
- `_run_create_reservation` now validates the slot_id before any DB work.
- Replaced the read-check-insert pattern with a single atomic `INSERT … SELECT … WHERE capacity_check` statement. If no row is returned (`RETURNING id` yields `None`), the slot was full and an error is returned. Closes the overbooking read-before-insert race for single-process deployments.

**`mcp/mcp_server.py`:**
- Same `_validate_slot_id` helper added (mirrors `reservation_tools.py`).
- `create_reservation` tool now validates the slot_id and uses the conditional INSERT pattern with `RETURNING id` — raises HTTP 422 for invalid slots, HTTP 409 when the slot is full.

**`staff/app.py`:**
- Imported `logger` from `utils`.
- `confirm_reservation`, `deny_reservation`, `cancel_reservation` now log a warning when `send_message` returns `None` (Twilio send failed), so silent notification failures are visible in logs.

**`tests/test_e2e_whatsapp.py`:**
- `MockClient.create()` updated to accept `*args, **kwargs` — matches the real OpenAI call that passes `tools=` and `tool_choice=`.
- `DummyOpenAIResponse` now includes `finish_reason="stop"` and `message.tool_calls = None` — required by the tool-call loop.
- Dependency override key changed to import `get_db` from `models.models` directly (same object FastAPI registered).
- Added `web._skip_twilio_validation = True` in setUp / reset in tearDown.
- Added new test: `test_duplicate_inbound_sid_is_idempotent` — verifies duplicate deliveries return 200 and do not create a second message record.

**`tests/test_mcp_tools.py`:**
- Fixed reservations table DDL: added `status`, `guest_name`, `occasion`, `guest_phone`, `note`, `note_author` columns; removed incorrect `UNIQUE` on `slot_id` (multiple bookings per slot are valid up to capacity).
- Added 5 regression tests:
  - `test_invalid_slot_format_rejected` — malformed slot_ids get HTTP 422
  - `test_slot_outside_hours_rejected` — slots outside business hours get HTTP 422
  - `test_slot_misaligned_to_interval_rejected` — misaligned slots get HTTP 422
  - `test_second_booking_exceeding_capacity_fails` — overbooking attempt gets HTTP 409
  - `test_second_booking_within_capacity_succeeds` — multiple bookings within capacity succeed

**Test results:** 12/12 pass locally.

**Residual risks documented:**
- The conditional INSERT approach closes the race for single-process deployments (single uvicorn worker). For multi-process (multiple workers), a true DB-level lock (e.g., `pg_advisory_xact_lock` or `SERIALIZABLE` transaction isolation) is required to fully prevent overbooking — not yet implemented.
- The `ResourceWarning: unclosed database` lines in MCP async tests are a SQLAlchemy/SQLite cleanup issue in the test harness and do not indicate test failures.

---

---

### 2026-03-25 — Security hardening + staff webapp + deployment packaging

**What changed:**

**New files created:**
- `security.py` — Three-layer prompt injection protection: regex input detection, hardened system prompt builder, output PII regex scrubber. Prevents WhatsApp users from extracting client data via LLM manipulation.
- `rate_limiter.py` — In-memory sliding window rate limiter. Default: 10 messages per 60 seconds per phone number. Configurable via `RATE_LIMIT_COUNT` / `RATE_LIMIT_WINDOW` env vars.
- `staff/__init__.py` — Package marker.
- `staff/app.py` — Staff webapp APIRouter. Routes: login, logout, dashboard, reservation list + cancel, settings (toggle on/off, hours, capacity), client profile.
- `staff/auth.py` — Cookie-based session auth using `itsdangerous`. Sessions signed with `SECRET_KEY`. 8-hour TTL. `manager`/`owner` required for settings route.
- `staff/templates/base.html` — Shared nav + CSS for all staff pages.
- `staff/templates/login.html` — Login page (standalone, no nav).
- `staff/templates/dashboard.html` — Today's reservations, cover count, quick enable/disable toggle.
- `staff/templates/reservations.html` — Date-filtered reservation list with cancel buttons.
- `staff/templates/settings.html` — Full reservation settings form (hours, capacity, on/off).
- `staff/templates/client.html` — Read-only client profile page.
- `Dockerfile` — `python:3.11-slim`, installs deps, runs uvicorn on port 8000.
- `Procfile` — `web: uvicorn webapp:app --host 0.0.0.0 --port $PORT` for Heroku/Railway.
- `.env.example` — Template of all required environment variables.
- `CLAUDE.md` — AI agent instruction file.
- `dev.md` — Developer reference, run instructions, problem list.
- `updates.md` — This file.

**Modified files:**
- `webapp.py` — Added: Twilio HMAC webhook signature verification, per-phone rate limiting, prompt injection check, output PII filter, hardened system prompt (via `security.py`). Imports staff router and mounts it. Removed inline `get_db` definition.
- `mcp/mcp_server.py` — Reservation tools now read `reservation_settings` from DB. `list_open_times` generates slots dynamically from DB hours/interval and filters out full slots by summing existing `party_size`. `check_availability` and `create_reservation` enforce `reservations_enabled` and `max_per_slot`. Removed hardcoded 17:00–21:00 window.
- `models/models.py` — Added `ReservationSettings` ORM model. Added `get_db()` generator (moved from `webapp.py` to break circular import).
- `models/employees.py` — Added `hash_password()` / `verify_password()` (bcrypt). `create_employee()` now hashes password before storing. Added `get_employee_by_username()`.
- `database/schema.py` — Added `reservation_settings` table DDL.
- `manage.py` — Added `seed_reservation_settings()`. Called on fresh init and `--reset`.
- `requirements.txt` — Added `bcrypt`, `itsdangerous`, `jinja2`. Removed duplicate `psycopg`.

**Why:** Moving toward a deployable beta. The system lacked any staff UI, any security hardening, and any deployment config. These changes address all three.

---

### 2026-03-25 — Architectural cleanup + bug fixes

**What changed:**

**Bug fixed:**
- `models/restaurants.py`, `models/employees.py`, `models/history.py`, `models/notes.py` — All had `db: Session = SessionLocal()` as a default parameter. This evaluated `SessionLocal()` once at import time, creating a single shared session for all callers. Fixed to `db: Optional[Session] = None` with `if db is None: db = SessionLocal()` inside each function body.

**Circular import broken:**
- `get_db()` moved from `webapp.py` to `models/models.py`. `mcp/mcp_server.py` no longer imports from `webapp.py` for this dependency.

**Dead code removed:**
- `api/routes.py/` — Ghost directory (named like a file) containing two 0-byte files. Deleted.
- `api/routes/clients.py` — All endpoints were commented out. Deleted.
- `api/routes/visits.py` — Empty. Deleted.
- `api/md_api.py` — Only contained imports, no logic. Deleted.

**Unused imports removed:**
- `mcp/mcp_server.py` — Removed `and_`, `time as dtime`, `SessionLocal` (all unused).

**Why:** The shared-session bug was a runtime correctness issue that would cause stale data and concurrency errors. The dead code removal reduces confusion during development.

---

### Prior sessions — Initial build

**Core system built:**
- WhatsApp → Twilio → FastAPI `/message` endpoint
- Conversation threading with 24-hour TTL
- Message idempotency via Twilio MessageSid
- GPT-4o-mini integration with 20-message context window
- PostgreSQL schema: conversations, messages, clients, restaurants, employees, history, notes, reservations
- MCP tools for reservation flow (original hardcoded version)
- PII redaction in logs (SHA256 hash of phone numbers)
- `manage.py` CLI for DB init/reset
- Unit tests for conversations, e2e WhatsApp flow, MCP tools

---

## Known Issues Introduced (not yet fixed)

- `webapp.py` imports `StaticFiles` from fastapi but never uses it — dead import
- `mcp/mcp_server.py` uses Pydantic v1 `@validator` (deprecated in v2) — non-breaking but noisy
- Staff session cookie has `secure=False` — must be `True` in production (HTTPS required)
- Rate limiter is in-memory — data lost on server restart, not safe for multi-process
- No Alembic — schema changes require `--reset` or manual `ALTER TABLE`

---

## Environment Variable Checklist

Before running in any environment, confirm these are set:

- [ ] `DATABASE_URL`
- [ ] `OPENAI_API_KEY`
- [ ] `TWILIO_ACCOUNT_SID`
- [ ] `TWILIO_AUTH_TOKEN`
- [ ] `TWILIO_NUMBER`
- [ ] `SECRET_KEY` (generate: `python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `TWILIO_SKIP_VALIDATION=true` (local dev only — must be `false` in production)
- [ ] `APP_TIMEZONE` (e.g. `America/Mexico_City`)
