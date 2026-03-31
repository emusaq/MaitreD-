# Standard library import
import json
import logging
from typing import Optional

# Third-party imports
from twilio.rest import Client
import hashlib
import uuid

from config import (
    TWILIO_ACCOUNT_SID as account_sid,
    TWILIO_AUTH_TOKEN as auth_token,
    TWILIO_NUMBER as twilio_number,
    TWILIO_CONFIRM_TEMPLATE_SID as _confirm_template_sid,
    TWILIO_DENY_TEMPLATE_SID as _deny_template_sid,
    TWILIO_CANCEL_TEMPLATE_SID as _cancel_template_sid,
)

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
def send_message(to_number: str, body_text: str) -> Optional[str]:
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


def send_template_message(
    to_number: str,
    template_sid: str,
    template_variables: Optional[dict] = None,
) -> Optional[str]:
    """Send a pre-approved WhatsApp Business template message via Twilio Content API.

    Required for out-of-session sends (>24h since last inbound from this number).
    template_variables: dict of positional variables, e.g. {"1": "7:00 PM", "2": "4 guests"}.
    """
    if not _twilio_enabled or client is None:
        logger.warning("Twilio not configured; skipping template send.")
        return None
    if not template_sid:
        logger.warning("send_template_message called with no template_sid; skipping.")
        return None
    try:
        params: dict = {
            "from_": f"whatsapp:{twilio_number}",
            "to": f"whatsapp:{to_number}",
            "content_sid": template_sid,
        }
        if template_variables:
            params["content_variables"] = json.dumps(template_variables)
        message = client.messages.create(**params)
        logger.info(f"Template message sent to hash:{redact_pii(to_number)}")
        return message.sid
    except Exception as e:
        logger.error(f"Error sending template message to hash:{redact_pii(to_number)}: {e}")
        return None
