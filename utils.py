"""Utility helpers for messaging and phone number handling."""

# Standard library imports
import logging
import re
from typing import Optional

# Third-party imports are optional so tests can run without them
try:  # pragma: no cover - simple import guard
    from twilio.rest import Client
except Exception:  # noqa: BLE001 - broad to avoid hard dependency during tests
    Client = None  # type: ignore[assignment]

try:  # pragma: no cover - simple import guard
    from decouple import config
except Exception:  # noqa: BLE001
    def config(*args, **kwargs):  # type: ignore[override]
        return None


# Attempt to configure a Twilio client if credentials are available
account_sid = config("TWILIO_ACCOUNT_SID", default=None)
auth_token = config("TWILIO_AUTH_TOKEN", default=None)
twilio_number = config("TWILIO_NUMBER", default=None)

twilio_client: Optional[Client] = None
if Client and account_sid and auth_token:
    try:
        twilio_client = Client(account_sid, auth_token)
    except Exception:  # noqa: BLE001
        twilio_client = None


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_phone(raw: str) -> Optional[str]:
    """Normalize raw phone text into E.164 format.

    Returns ``None`` if the input cannot be interpreted as a phone number.
    Only very small amount of validation is performed and assumes US numbers
    when a country code is not supplied.
    """

    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)

    if raw.strip().startswith("+"):
        return f"+{digits}" if digits else None

    if len(digits) == 10:
        return f"+1{digits}"

    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    return None


def mask_phone(e164: str) -> str:
    """Mask an E.164 phone number leaving country code and last two digits."""

    if not e164 or not e164.startswith("+"):
        return e164

    head = e164[:2]
    tail = e164[-2:]
    return f"{head}{'*' * (len(e164) - len(head) - len(tail))}{tail}"


def simulate_send(sender_id: str, text: str) -> None:
    """Fallback message send that simply prints to stdout."""

    print(f"[SIMULATED SEND] to {sender_id}: {text}")


# Sending message logic through Twilio Messaging API
def send_message(to_number: str, body_text: str) -> None:
    """Send a message via Twilio if configured, otherwise simulate."""

    normalized = normalize_phone(to_number)
    if not normalized:
        logger.error(f"Invalid phone number: {to_number}")
        return

    if twilio_client and twilio_number:
        try:
            message = twilio_client.messages.create(
                from_=f"whatsapp:{twilio_number}",
                body=body_text,
                to=f"whatsapp:{normalized}",
            )
            logger.info(f"Message sent to {normalized}: {message.body}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Error sending message to {normalized}: {exc}")
    else:
        simulate_send(normalized, body_text)
