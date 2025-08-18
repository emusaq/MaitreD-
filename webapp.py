# Third-party imports
from openai import OpenAI, OpenAIError, RateLimitError
from fastapi import FastAPI, Form, Depends, Request
from decouple import config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os


# Internal imports
from models.models import Conversation, Message, SessionLocal
from utils import send_message, logger, redact_pii, new_trace_id


app = FastAPI()
# Set up the OpenAI API client
client = OpenAI(api_key=config("OPENAI_API_KEY"))

# Dependency
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


@app.get("/")
async def index():
    return {"msg": "working"}

@app.post("/message")
async def reply(request: Request, Body: str = Form(), db: Session = Depends(get_db)):
    try:
        trace_id = new_trace_id()
        # Extract form data
        form_data = await request.form()
        whatsapp_number = form_data.get('From', '').split("whatsapp:")[-1]
        body_text = form_data.get('Body', '')
        inbound_sid = form_data.get('MessageSid')

        if not whatsapp_number or not body_text:
            logger.error(f"[{trace_id}] Missing 'From' or 'Body' in incoming request")
            return {"error": "Invalid request: missing sender or message body"}

        logger.info(f"[{trace_id}] inbound received from hash:{redact_pii(whatsapp_number)}")

        # Check idempotency for inbound messages (Twilio MessageSid)
        if inbound_sid:
            existing = db.query(Message).filter(Message.external_message_id == inbound_sid).first()
            if existing:
                logger.info(f"[{trace_id}] duplicate inbound MessageSid; ignoring")
                return {"status": "ok", "idempotent": True}

        # Find or create a conversation for this sender within TTL
        ttl_hours = int(os.getenv("CONVERSATION_TTL_HOURS", "24"))
        tz = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Ciudad_Juarez"))
        now_local = datetime.now(tz)
        now = now_local.replace(tzinfo=None)
        ttl_cutoff = now - timedelta(hours=ttl_hours)

        convo = (
            db.query(Conversation)
            .filter(
                Conversation.channel == 'whatsapp',
                Conversation.external_user_id == whatsapp_number,
            )
            .order_by(Conversation.updated_at.desc())
            .first()
        )

        if convo and convo.updated_at and convo.updated_at >= ttl_cutoff:
            logger.info(f"[{trace_id}] reuse conversation_id={convo.id}")
        else:
            convo = Conversation(
                channel='whatsapp',
                external_user_id=whatsapp_number,
                opened_at=now,
                updated_at=now,
                status='open',
            )
            db.add(convo)
            db.flush()
            logger.info(f"[{trace_id}] created new conversation_id={convo.id}")

        # Persist inbound message
        inbound_msg = Message(
            conversation_id=convo.id,
            direction='inbound',
            text=body_text,
            external_message_id=inbound_sid,
        )
        db.add(inbound_msg)
        db.flush()

        # Build conversation history for model
        history_msgs = []
        recent_messages = (
            db.query(Message)
            .filter(Message.conversation_id == convo.id)
            .order_by(Message.created_at.asc())
            .limit(20)
            .all()
        )
        for m in recent_messages:
            role = 'user' if m.direction == 'inbound' else 'assistant'
            history_msgs.append({"role": role, "content": m.text})

        # Prepare system message with current_date context
        current_date = now_local.date().isoformat()
        system_text = (
            "You're a receptionist for Garufa, a high-end Argentine restaurant. "
            "You make reservations and answer customer questions. "
            f"Current date (ISO): {current_date}. Interpret relative dates from this."
        )
        messages = ([{"role": "system", "content": system_text}] + history_msgs)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=200,
                temperature=0.5
            )
            chatgpt_response = response.choices[0].message.content.strip()
        except RateLimitError:
            chatgpt_response = "⚠ Sorry, I'm currently overloaded. Please try again later."
            logger.warning(f"[{trace_id}] OpenAI RateLimitError: quota exceeded")
        except OpenAIError as e:
            chatgpt_response = f"⚠ OpenAI error: {str(e)}"
            logger.error(f"[{trace_id}] OpenAI API error: {e}")
        except Exception as e:
            chatgpt_response = f"⚠ Unexpected server error."
            logger.error(f"[{trace_id}] Unexpected error during OpenAI call: {e}")

        # Store outbound message and update conversation timestamp
        try:
            outbound_msg = Message(
                conversation_id=convo.id,
                direction='outbound',
                text=chatgpt_response,
            )
            db.add(outbound_msg)
            convo.updated_at = now
            db.commit()
            logger.info(f"[{trace_id}] stored inbound/outbound messages for conversation_id={convo.id}")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[{trace_id}] Database error storing messages: {e}")

        # Send reply back to user
        try:
            sid = send_message(whatsapp_number, chatgpt_response)
            # Record outbound SID if available
            if sid:
                db.query(Message).filter(Message.id == outbound_msg.id).update({Message.external_message_id: sid})
                db.commit()
                logger.info(f"[{trace_id}] outbound sent sid={sid}")
        except Exception as e:
            logger.error(f"[{trace_id}] Failed to send message to hash:{redact_pii(whatsapp_number)}: {e}")

        return {"status": "ok", "conversation_id": convo.id, "trace_id": trace_id}

    except Exception as e:
        logger.error(f"[{trace_id}] Critical error in /message endpoint: {e}")
        return {"error": "Critical server error."}
