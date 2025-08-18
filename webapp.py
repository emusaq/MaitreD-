from openai import OpenAI, OpenAIError, RateLimitError
from fastapi import FastAPI, Form, Depends, Request
from decouple import config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Internal imports
from models import Conversation, SessionLocal
from models import client as client_model
from models import reservations as reservation_model
from utils import send_message, logger

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
        # Extract form data
        form_data = await request.form()
        whatsapp_number = form_data.get('From', '').split("whatsapp:")[-1]
        body_text = form_data.get('Body', '')

        if not whatsapp_number or not body_text:
            logger.error("Missing 'From' or 'Body' in incoming request")
            return {"error": "Invalid request: missing sender or message body"}

        print(f"Sending the ChatGPT response to this number: {whatsapp_number}")

        # Prepare messages for OpenAI
        messages = [
            {
                "role": "system",
                "content": (
                    "You're a receptionist and in charge of customer experience at a high end argentinean "
                    "restaurant called garufa, you make reservations and answer customer questions."
                ),
            },
        ]

        # Prepend FYI line if an upcoming reservation exists
        client_row = client_model.get_client_by_phone(whatsapp_number)
        if client_row:
            upcoming = reservation_model.get_upcoming_reservation(client_row[0])
            if upcoming:
                res_time = upcoming["reservation_time"].strftime("%Y-%m-%d %H:%M")
                fyi_line = f"FYI: You have a reservation on {res_time} for {upcoming['covers']} people."
                messages.append({"role": "system", "content": fyi_line})

        messages.append({"role": "user", "content": body_text})

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
            logger.warning("OpenAI RateLimitError: quota exceeded")
        except OpenAIError as e:
            chatgpt_response = f"⚠ OpenAI error: {str(e)}"
            logger.error(f"OpenAI API error: {e}")
        except Exception as e:
            chatgpt_response = f"⚠ Unexpected server error."
            logger.error(f"Unexpected error during OpenAI call: {e}")

        # Store conversation in the database
        try:
            conversation = Conversation(
                sender=whatsapp_number,
                message=body_text,
                response=chatgpt_response
            )
            db.add(conversation)
            db.commit()
            logger.info(f"Conversation #{conversation.id} stored in database")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error storing conversation: {e}")

        # Send reply back to user
        try:
            send_message(whatsapp_number, chatgpt_response)
        except Exception as e:
            logger.error(f"Failed to send message to {whatsapp_number}: {e}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Critical error in /message endpoint: {e}")
        return {"error": "Critical server error."}
