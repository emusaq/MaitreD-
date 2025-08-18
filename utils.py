# Standard library import
import logging

# Third-party imports
from twilio.rest import Client
from decouple import config
import hashlib
import uuid


# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = config(TWILIO_ACCOUNT_SID)
auth_token = config("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)
twilio_number = config('TWILIO_NUMBER')

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
