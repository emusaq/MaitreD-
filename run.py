#!/usr/bin/env python3
"""
Maitred server management

    python run.py start    — health checks + start server
    python run.py reload   — stop + restart (picks up code changes)
    python run.py quit     — stop the server
"""

import os
import sys
import signal
import socket
import subprocess
import time
from pathlib import Path

# ── paths & config ──────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
PID_FILE  = ROOT / ".maitred.pid"
LOG_FILE  = Path("/tmp/maitred.log")
PORT      = 8000

# ── colour helpers ──────────────────────────────────────────────────────────
def _g(t): return f"\033[32m{t}\033[0m"   # green
def _r(t): return f"\033[31m{t}\033[0m"   # red
def _y(t): return f"\033[33m{t}\033[0m"   # yellow
def _b(t): return f"\033[1m{t}\033[0m"    # bold

def ok(msg):   print(f"  {_g('✓')} {msg}")
def fail(msg): print(f"  {_r('✗')} {msg}"); sys.exit(1)
def warn(msg): print(f"  {_y('!')} {msg}")
def info(msg): print(f"  {_b('→')} {msg}")


# ── pid helpers ──────────────────────────────────────────────────────────────
def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def _kill(pid: int, name: str = "server") -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):          # wait up to 2 s
            time.sleep(0.1)
            if not _is_running(pid):
                return True
        os.kill(pid, signal.SIGKILL) # force-kill if still alive
        return True
    except ProcessLookupError:
        return True
    except Exception as e:
        warn(f"Could not stop {name}: {e}")
        return False


# ── startup checks ───────────────────────────────────────────────────────────
REQUIRED_VARS = [
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_NUMBER",
    "SECRET_KEY",
]

def _load_env():
    """Load .env via python-decouple without importing the whole app."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        fail(".env file not found — copy .env.example and fill in values")
    # Simple parser: set vars into os.environ so decouple picks them up
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

def _check_env():
    print(_b("Checking environment variables..."))
    _load_env()
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        for m in missing:
            warn(f"{m} is not set")
        fail("Missing required environment variables. Check your .env file.")
    ok(f"All {len(REQUIRED_VARS)} required variables present")

def _check_db():
    print(_b("Checking database connection..."))
    try:
        import psycopg2
        db_url = os.environ.get("MAITRED_DB") or os.environ.get("DATABASE_URL", "")
        # Build a psycopg2 DSN from DATABASE_URL if needed
        if db_url.startswith("postgresql"):
            # Parse sqlalchemy URL → psycopg2 DSN
            from urllib.parse import urlparse
            p = urlparse(db_url.replace("postgresql+psycopg2://", "postgresql://"))
            conn = psycopg2.connect(
                host=p.hostname, port=p.port or 5432,
                dbname=p.path.lstrip("/"),
                user=p.username, password=p.password,
            )
        else:
            conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
        table_count = cur.fetchone()[0]
        conn.close()
        ok(f"PostgreSQL connected — {table_count} tables found")
    except Exception as e:
        fail(f"Database connection failed: {e}")

def _check_openai():
    print(_b("Checking OpenAI..."))
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or key in ('""', "''", ""):
        fail("OPENAI_API_KEY is empty")
    if not key.startswith("sk-"):
        warn("OPENAI_API_KEY looks unusual (does not start with 'sk-')")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        ok(f"OpenAI API responding (model: gpt-4o-mini)")
    except Exception as e:
        fail(f"OpenAI check failed: {e}")

def _check_twilio():
    print(_b("Checking Twilio..."))
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    number = os.environ.get("TWILIO_NUMBER", "")
    if not sid.startswith("AC"):
        fail("TWILIO_ACCOUNT_SID looks wrong (should start with 'AC')")
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        account = client.api.accounts(sid).fetch()
        ok(f"Twilio connected — account: {account.friendly_name}")
        ok(f"WhatsApp number: {number}")
    except Exception as e:
        fail(f"Twilio check failed: {e}")

def _check_port():
    print(_b(f"Checking port {PORT}..."))
    pid = _read_pid()
    if pid and _is_running(pid):
        fail(f"Port {PORT} is already in use by Maitred (PID {pid}). Run 'reload' or 'quit' first.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            fail(f"Port {PORT} is in use by another process. Free it before starting.")
    ok(f"Port {PORT} is free")


# ── commands ─────────────────────────────────────────────────────────────────
def cmd_start():
    print()
    print(_b("━━━  Maitred Startup  ━━━"))
    print()

    _check_env()
    _check_db()
    _check_openai()
    _check_twilio()
    _check_port()

    print()
    print(_b("Starting server..."))

    log_handle = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp:app",
         "--host", "0.0.0.0", "--port", str(PORT), "--reload"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    PID_FILE.write_text(str(proc.pid))

    # Wait for server to become reachable
    for attempt in range(20):
        time.sleep(0.5)
        if not _is_running(proc.pid):
            print()
            fail(f"Server process exited unexpectedly. Check logs: tail -f {LOG_FILE}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                break
    else:
        fail(f"Server did not become reachable on port {PORT}. Check logs: tail -f {LOG_FILE}")

    print()
    ok(f"Server running  (PID {proc.pid})")
    info(f"Staff portal    →  http://localhost:{PORT}/staff/login")
    info(f"Webhook URL     →  http://localhost:{PORT}/message  (POST)")
    info(f"Health check    →  http://localhost:{PORT}/")
    info(f"Logs            →  tail -f {LOG_FILE}")
    print()


def cmd_reload():
    print()
    print(_b("━━━  Maitred Reload  ━━━"))
    print()

    pid = _read_pid()
    if pid and _is_running(pid):
        print(_b("Stopping current server..."))
        if _kill(pid):
            ok(f"Stopped PID {pid}")
        PID_FILE.unlink(missing_ok=True)
        time.sleep(0.5)
    else:
        warn("No running server found — starting fresh")
        if PID_FILE.exists():
            PID_FILE.unlink()

    cmd_start()


def cmd_quit():
    print()
    print(_b("━━━  Maitred Shutdown  ━━━"))
    print()

    pid = _read_pid()
    if not pid:
        warn("No PID file found — server may not be running")
        sys.exit(0)

    if not _is_running(pid):
        warn(f"PID {pid} is not running — cleaning up")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    print(_b("Stopping server..."))
    if _kill(pid):
        PID_FILE.unlink(missing_ok=True)
        ok(f"Server stopped  (was PID {pid})")
    else:
        fail(f"Could not stop PID {pid} — try: kill -9 {pid}")

    print()


def cmd_clear_history():
    print()
    print(_b("━━━  Clear Chat History  ━━━"))
    print()

    _load_env()
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        fail("DATABASE_URL is not set")

    print(_b("Connecting to database..."))
    try:
        import psycopg2
        from urllib.parse import urlparse
        p = urlparse(db_url.replace("postgresql+psycopg2://", "postgresql://"))
        conn = psycopg2.connect(
            host=p.hostname, port=p.port or 5432,
            dbname=p.path.lstrip("/").split("?")[0],
            user=p.username, password=p.password,
        )
    except Exception as e:
        fail(f"Database connection failed: {e}")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages;")
    msg_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM conversations;")
    convo_count = cur.fetchone()[0]

    print()
    warn(f"This will permanently delete {msg_count} messages across {convo_count} conversations.")
    answer = input(f"  {_y('?')} Type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        print()
        info("Aborted — nothing was deleted.")
        print()
        conn.close()
        sys.exit(0)

    cur.execute("DELETE FROM messages;")
    cur.execute("DELETE FROM conversations;")
    conn.commit()
    conn.close()

    print()
    ok(f"Deleted {msg_count} messages and {convo_count} conversations")
    info("Reservations and client records were not affected")
    print()


# ── entrypoint ────────────────────────────────────────────────────────────────
COMMANDS = {
    "start":         cmd_start,
    "reload":        cmd_reload,
    "quit":          cmd_quit,
    "clear-history": cmd_clear_history,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python run.py [{' | '.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
