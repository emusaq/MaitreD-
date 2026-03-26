# Standard library import
import logging

# Third-party imports
from twilio.rest import Client
from decouple import config
import hashlib
import uuid


# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = config('TWILIO_ACCOUNT_SID', default=None)
auth_token = config("TWILIO_AUTH_TOKEN", default=None)
twilio_number = config('TWILIO_NUMBER', default=None)
_twilio_enabled = bool(account_sid and auth_token and twilio_number)
client = Client(account_sid, auth_token) if _twilio_enabled else None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def redact_pii(value: str) -> str:
    """Return a hashed token for PII (e.g., phone numbers) for logs."""
    if value is None:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]

def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]

# Sending message logic through Twilio Messaging API
def send_message(to_number, body_text):
    if not _twilio_enabled or client is None:
        logger.warning("Twilio not configured; skipping send.")
        return None
    try:
        message = client.messages.create(
            from_=f"whatsapp:{twilio_number}",
            body=body_text,
            to=f"whatsapp:{to_number}"
            )
        logger.info(f"Message sent to hash:{redact_pii(to_number)}")
        return message.sid
    except Exception as e:
        logger.error(f"Error sending message to hash:{redact_pii(to_number)}: {e}")
        return None
