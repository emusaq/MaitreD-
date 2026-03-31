"""Central configuration module.

All environment variable reads are consolidated here. Importing this module
validates required variables at startup so misconfigurations fail fast.

Usage in other modules:
    from config import DATABASE_URL, SECRET_KEY, ...
"""
import warnings
from typing import Optional

from decouple import config

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL: Optional[str] = config("DATABASE_URL", default=None)
DB_USER: Optional[str] = config("DB_USER", default=None)
DB_PASSWORD: Optional[str] = config("DB_PASSWORD", default=None)

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY: Optional[str] = config("OPENAI_API_KEY", default=None)
OPENAI_MODEL: str = config("OPENAI_MODEL", default="gpt-4o-mini")
OPENAI_TEMPERATURE: float = config("OPENAI_TEMPERATURE", default=0.2, cast=float)
OPENAI_MAX_TOKENS: int = config("OPENAI_MAX_TOKENS", default=300, cast=int)

# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID: Optional[str] = config("TWILIO_ACCOUNT_SID", default=None)
TWILIO_AUTH_TOKEN: Optional[str] = config("TWILIO_AUTH_TOKEN", default=None)
TWILIO_NUMBER: Optional[str] = config("TWILIO_NUMBER", default=None)
TWILIO_CONFIRM_TEMPLATE_SID: Optional[str] = config("TWILIO_CONFIRM_TEMPLATE_SID", default=None) or None
TWILIO_DENY_TEMPLATE_SID: Optional[str] = config("TWILIO_DENY_TEMPLATE_SID", default=None) or None
TWILIO_CANCEL_TEMPLATE_SID: Optional[str] = config("TWILIO_CANCEL_TEMPLATE_SID", default=None) or None
TWILIO_SKIP_VALIDATION: bool = config("TWILIO_SKIP_VALIDATION", default="false").lower() == "true"

# ---------------------------------------------------------------------------
# App behavior
# ---------------------------------------------------------------------------
SECRET_KEY: str = config("SECRET_KEY", default="change-me-in-production")
SECURE_COOKIES: bool = config("SECURE_COOKIES", default="true").lower() == "true"
RATE_LIMIT_COUNT: int = config("RATE_LIMIT_COUNT", default=10, cast=int)
RATE_LIMIT_WINDOW: int = config("RATE_LIMIT_WINDOW", default=60, cast=int)
REDIS_URL: Optional[str] = config("REDIS_URL", default=None)
CONVERSATION_TTL_HOURS: int = config("CONVERSATION_TTL_HOURS", default=24, cast=int)
CONVERSATION_HISTORY_LIMIT: int = config("CONVERSATION_HISTORY_LIMIT", default=12, cast=int)
MAX_TOOL_ROUNDS: int = config("MAX_TOOL_ROUNDS", default=5, cast=int)
APP_TIMEZONE: str = config("APP_TIMEZONE", default="America/Ciudad_Juarez")

# ---------------------------------------------------------------------------
# Restaurant identity
# ---------------------------------------------------------------------------
RESTAURANT_NAME: str = config("RESTAURANT_NAME", default="Garufa")
RESTAURANT_DESCRIPTION: str = config("RESTAURANT_DESCRIPTION", default="Garufa is an argentinean steakhouse that prides itself in its service and hospitality while offering a fine dining experience. Our ultimate goal is to make every customer leave happier than they came in")
CONCIERGE_TONE: str = config("CONCIERGE_TONE", default="warm, polished, and attentive")
INJECTION_REPLY: str = config("INJECTION_REPLY", default="I can only help with reservations. How can I assist you?")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    """Return a full SQLAlchemy database URL from config, or raise EnvironmentError."""
    if DATABASE_URL:
        return DATABASE_URL
    if DB_USER and DB_PASSWORD:
        from sqlalchemy.engine import URL as _URL
        return str(_URL.create(
            drivername="postgresql",
            username=DB_USER,
            password=DB_PASSWORD,
            host="localhost",
            database="maitred",
            port=5433,
        ))
    raise EnvironmentError(
        "Database not configured. Set DATABASE_URL or both DB_USER and DB_PASSWORD."
    )


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def _validate() -> None:
    # Fail fast if no database config is present at all
    if not DATABASE_URL and not (DB_USER and DB_PASSWORD):
        raise EnvironmentError(
            "Database not configured. Set DATABASE_URL or both DB_USER and DB_PASSWORD."
        )
    # Warn (not raise) so tests without a real secret key still run
    if SECRET_KEY == "change-me-in-production":
        warnings.warn(
            "SECRET_KEY is set to the default value. "
            "Generate a strong random key before deploying to production.",
            stacklevel=2,
        )


_validate()
