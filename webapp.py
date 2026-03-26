# Third-party imports
from openai import OpenAI, OpenAIError, RateLimitError
from fastapi import FastAPI, Form, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from decouple import config
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from twilio.request_validator import RequestValidator
# Internal imports
import json
from models.models import Conversation, Message, ReservationSettings, get_db
from utils import send_message, logger, redact_pii, new_trace_id
from security import sanitize_input, filter_output, build_system_prompt, INJECTION_REPLY
from rate_limiter import is_allowed
from reservation_tools import OPENAI_TOOLS, execute_tool
from staff.app import router as staff_router


app = FastAPI()
app.include_router(staff_router)

# Set up the OpenAI API client (tolerate missing key during import for tests)
_openai_key = config("OPENAI_API_KEY", default=None)
if _openai_key:
    client = OpenAI(api_key=_openai_key)
else:
    class _NoOpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    raise RuntimeError("OPENAI_API_KEY not set")
    client = _NoOpenAI()

# Twilio webhook validator (used in /message)
_twilio_auth_token = config("TWILIO_AUTH_TOKEN", default=None)
_twilio_validator = RequestValidator(_twilio_auth_token) if _twilio_auth_token else None
_skip_twilio_validation = config("TWILIO_SKIP_VALIDATION", default="false").lower() == "true"

# AI model settings
_openai_model = config("OPENAI_MODEL", default="gpt-4o-mini")
_openai_temperature = config("OPENAI_TEMPERATURE", default=0.2, cast=float)
_openai_max_tokens = config("OPENAI_MAX_TOKENS", default=300, cast=int)
_history_limit = config("CONVERSATION_HISTORY_LIMIT", default=12, cast=int)
_max_tool_rounds = config("MAX_TOOL_ROUNDS", default=5, cast=int)


@app.get("/")
async def index():
    return {"msg": "working"}


@app.post("/message")
async def reply(request: Request, Body: str = Form(), db: Session = Depends(get_db)):
    trace_id = new_trace_id()
    try:
        form_data = await request.form()

        # --- Twilio webhook signature verification ---
        if not _skip_twilio_validation:
            if _twilio_validator is None:
                logger.error(f"[{trace_id}] TWILIO_AUTH_TOKEN not configured")
                raise HTTPException(status_code=500, detail="Server misconfiguration")
            signature = request.headers.get("X-Twilio-Signature", "")
            url = str(request.url)
            if not _twilio_validator.validate(url, dict(form_data), signature):
                logger.warning(f"[{trace_id}] Invalid Twilio signature — request rejected")
                raise HTTPException(status_code=403, detail="Forbidden")

        # Extract form data
        whatsapp_number = form_data.get('From', '').split("whatsapp:")[-1]
        body_text = form_data.get('Body', '')
        inbound_sid = form_data.get('MessageSid')

        if not whatsapp_number or not body_text:
            logger.error(f"[{trace_id}] Missing 'From' or 'Body' in incoming request")
            return {"error": "Invalid request: missing sender or message body"}

        logger.info(f"[{trace_id}] inbound received from hash:{redact_pii(whatsapp_number)}")

        # --- Per-phone rate limiting ---
        if not is_allowed(whatsapp_number):
            logger.warning(f"[{trace_id}] Rate limit exceeded for hash:{redact_pii(whatsapp_number)}")
            send_message(whatsapp_number, "You're sending messages too quickly. Please wait a moment and try again.")
            return JSONResponse(status_code=429, content={"status": "rate_limited"})

        # Fetch settings once — reused for pause check and system prompt below
        settings_row = db.query(ReservationSettings).first()

        # --- Chatbot pause check ---
        if settings_row and settings_row.chatbot_paused:
            logger.info(f"[{trace_id}] chatbot paused; sending away message to hash:{redact_pii(whatsapp_number)}")
            send_message(whatsapp_number, settings_row.paused_away_message)
            return {"status": "ok", "paused": True}

        # --- Prompt injection check ---
        body_text, was_flagged = sanitize_input(body_text)
        if was_flagged:
            logger.warning(f"[{trace_id}] Injection attempt from hash:{redact_pii(whatsapp_number)}")
            send_message(whatsapp_number, INJECTION_REPLY)
            return {"status": "ok", "flagged": True}

        # Check idempotency for inbound messages (Twilio MessageSid)
        if inbound_sid:
            existing = db.query(Message).filter(Message.external_message_id == inbound_sid).first()
            if existing:
                logger.info(f"[{trace_id}] duplicate inbound MessageSid; ignoring")
                return {"status": "ok", "idempotent": True}

        # Find or create a conversation for this sender within TTL
        ttl_hours = config("CONVERSATION_TTL_HOURS", default=24, cast=int)
        tz = ZoneInfo(config("APP_TIMEZONE", default="America/Ciudad_Juarez"))
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

        # Persist inbound message — catch IntegrityError to handle rare duplicate-SID races
        inbound_msg = Message(
            conversation_id=convo.id,
            direction='inbound',
            text=body_text,
            external_message_id=inbound_sid,
        )
        db.add(inbound_msg)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info(f"[{trace_id}] duplicate inbound MessageSid (race caught at DB); ignoring")
            return {"status": "ok", "idempotent": True}

        # Build conversation history for model — most recent messages in chronological order
        history_msgs = []
        recent_messages = (
            db.query(Message)
            .filter(Message.conversation_id == convo.id)
            .order_by(Message.created_at.desc())
            .limit(_history_limit)
            .all()
        )
        recent_messages.reverse()
        for m in recent_messages:
            role = 'user' if m.direction == 'inbound' else 'assistant'
            history_msgs.append({"role": role, "content": m.text})

        # Use settings fetched earlier for system prompt dynamic values
        large_party_threshold = settings_row.large_party_threshold if settings_row else 8
        large_party_phone = settings_row.large_party_phone if settings_row else ""

        # Prepare hardened system prompt
        current_date = now_local.date().isoformat()
        system_text = build_system_prompt(current_date, large_party_threshold, large_party_phone)
        messages = [{"role": "system", "content": system_text}] + history_msgs

        try:
            # Tool-call loop: keep calling until the model stops requesting tools
            for _ in range(_max_tool_rounds):
                response = client.chat.completions.create(
                    model=_openai_model,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                    max_tokens=_openai_max_tokens,
                    temperature=_openai_temperature,
                )
                choice = response.choices[0]

                if choice.finish_reason == "tool_calls":
                    # Append the assistant's tool-call message
                    messages.append(choice.message)
                    # Execute each tool and append results
                    for tc in choice.message.tool_calls:
                        result = execute_tool(tc.function.name, tc.function.arguments, db)
                        logger.info(f"[{trace_id}] tool={tc.function.name} result={result[:120]}")
                        # After a successful create_reservation, store the guest's phone
                        if tc.function.name == "create_reservation":
                            try:
                                result_dict = json.loads(result)
                                rid = result_dict.get("reservation_id")
                                if rid:
                                    from sqlalchemy import text as _text
                                    db.execute(
                                        _text("UPDATE reservations SET guest_phone = :phone WHERE id = :id"),
                                        {"phone": whatsapp_number, "id": rid},
                                    )
                                    db.commit()
                            except Exception as _e:
                                logger.error(f"[{trace_id}] Failed to write guest_phone: {_e}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                else:
                    # Model returned a final text response
                    break

            content = choice.message.content
            if not content:
                # Loop exhausted without a final text — shouldn't happen normally
                logger.warning(f"[{trace_id}] tool loop ended with no text response")
                content = "Lo siento, hubo un problema al procesar tu solicitud. Por favor intenta de nuevo."
            chatgpt_response = filter_output(content.strip())

        except RateLimitError:
            chatgpt_response = "⚠ Sorry, I'm currently overloaded. Please try again later."
            logger.warning(f"[{trace_id}] OpenAI RateLimitError: quota exceeded")
        except OpenAIError as e:
            chatgpt_response = "⚠ I'm having trouble right now. Please try again in a moment."
            logger.error(f"[{trace_id}] OpenAI API error: {e}")
        except Exception as e:
            chatgpt_response = "⚠ Unexpected server error."
            logger.error(f"[{trace_id}] Unexpected error during OpenAI call: {e}")

        # Store outbound message and update conversation timestamp
        outbound_msg = None
        outbound_persisted = False
        try:
            outbound_msg = Message(
                conversation_id=convo.id,
                direction='outbound',
                text=chatgpt_response,
            )
            db.add(outbound_msg)
            convo.updated_at = now
            db.commit()
            outbound_persisted = True
            logger.info(f"[{trace_id}] stored inbound/outbound messages for conversation_id={convo.id}")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[{trace_id}] Database error storing messages: {e}")

        # Send reply back to user; only update SID if the outbound row was persisted
        try:
            sid = send_message(whatsapp_number, chatgpt_response)
            if sid:
                logger.info(f"[{trace_id}] outbound sent sid={sid}")
                if outbound_persisted and outbound_msg is not None:
                    db.query(Message).filter(Message.id == outbound_msg.id).update({Message.external_message_id: sid})
                    db.commit()
        except Exception as e:
            logger.error(f"[{trace_id}] Failed to send message to hash:{redact_pii(whatsapp_number)}: {e}")

        return {"status": "ok", "conversation_id": convo.id, "trace_id": trace_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{trace_id}] Critical error in /message endpoint: {e}")
        return {"error": "Critical server error."}
