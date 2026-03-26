import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

import os
os.environ["SQLALCHEMY_CREATE_ALL"] = "0"
import webapp as web
from models.models import Base, Conversation, Message, get_db


class DummyOpenAIResponse:
    class Choice:
        class Msg:
            def __init__(self, content):
                self.content = content
                self.tool_calls = None  # required by tool-call loop
        def __init__(self, content):
            self.message = self.Msg(content)
            self.finish_reason = "stop"  # required by tool-call loop
    def __init__(self, content):
        self.choices = [self.Choice(content)]


class E2EWhatsAppTests(unittest.TestCase):
    def setUp(self):
        # Use file-based SQLite DB to allow cross-thread access
        db_path = './test_e2e.db'
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass
        self.engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Override dependency to provide a fresh session per request
        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        # Key must be the same function object FastAPI registered as the dependency
        web.app.dependency_overrides[get_db] = override_get_db

        # Bypass Twilio signature verification in tests
        web._skip_twilio_validation = True

        # Mock OpenAI client — accepts all kwargs the real call passes
        class MockClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(*args, **kwargs):
                        return DummyOpenAIResponse("ok")
        web.client = MockClient()

        # Mock Twilio send to avoid network calls
        web.send_message = lambda to, body: "SM_TEST_FAKE"

        self.client = TestClient(web.app)

    def tearDown(self):
        web.app.dependency_overrides.clear()
        web._skip_twilio_validation = False

    def test_two_messages_same_conversation_then_ttl_new(self):
        from_number = "+15551234567"
        # First message
        r1 = self.client.post("/message", data={"From": f"whatsapp:{from_number}", "Body": "Hi", "MessageSid": "SM1"})
        self.assertEqual(r1.status_code, 200)
        # Second message within TTL
        r2 = self.client.post("/message", data={"From": f"whatsapp:{from_number}", "Body": "Need a table", "MessageSid": "SM2"})
        self.assertEqual(r2.status_code, 200)

        # Assert one conversation, two inbound + two outbound messages
        db = self.SessionLocal()
        convos = db.query(Conversation).filter_by(channel='whatsapp', external_user_id=from_number).all()
        self.assertEqual(len(convos), 1)
        msgs = db.query(Message).filter(Message.conversation_id == convos[0].id).all()
        self.assertEqual(len(msgs), 4)  # 2 inbound + 2 outbound

        # Age the conversation beyond TTL and send a third message
        convos[0].updated_at = datetime.now() - timedelta(days=2)
        db.commit()

        r3 = self.client.post("/message", data={"From": f"whatsapp:{from_number}", "Body": "Another msg", "MessageSid": "SM3"})
        self.assertEqual(r3.status_code, 200)

        convos2 = db.query(Conversation).filter_by(channel='whatsapp', external_user_id=from_number).all()
        self.assertEqual(len(convos2), 2)
        db.close()

    def test_duplicate_inbound_sid_is_idempotent(self):
        """A duplicate Twilio delivery (same MessageSid) must not create a second record."""
        from_number = "+15559999001"
        r1 = self.client.post("/message", data={"From": f"whatsapp:{from_number}", "Body": "Hello", "MessageSid": "SM_DUP"})
        self.assertEqual(r1.status_code, 200)

        r2 = self.client.post("/message", data={"From": f"whatsapp:{from_number}", "Body": "Hello", "MessageSid": "SM_DUP"})
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("idempotent"), "Second delivery should be marked idempotent")

        db = self.SessionLocal()
        count = db.query(Message).filter(Message.external_message_id == "SM_DUP").count()
        self.assertEqual(count, 1, "Duplicate SID must produce exactly one message record")
        db.close()


if __name__ == '__main__':
    unittest.main()
