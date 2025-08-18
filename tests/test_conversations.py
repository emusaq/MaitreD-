import os
os.environ["SQLALCHEMY_CREATE_ALL"] = "0"
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.models import Base, Conversation, Message


class ConversationUnitTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_conversation_lookup_ttl(self):
        db = self.Session()
        now = datetime.now()
        # Create an old conversation beyond TTL
        old = Conversation(channel='whatsapp', external_user_id='123', opened_at=now - timedelta(days=2), updated_at=now - timedelta(days=2))
        db.add(old)
        db.commit()

        # TTL of 24h → should create a new conversation
        ttl_cutoff = now - timedelta(hours=24)
        convo = (
            db.query(Conversation)
            .filter(Conversation.channel == 'whatsapp', Conversation.external_user_id == '123')
            .order_by(Conversation.updated_at.desc())
            .first()
        )
        if convo and convo.updated_at and convo.updated_at >= ttl_cutoff:
            reused = True
        else:
            reused = False

        self.assertFalse(reused)

        # Update recent timestamp, expect reuse
        old.updated_at = now
        db.commit()
        convo2 = (
            db.query(Conversation)
            .filter(Conversation.channel == 'whatsapp', Conversation.external_user_id == '123')
            .order_by(Conversation.updated_at.desc())
            .first()
        )
        reused2 = convo2 and convo2.updated_at and convo2.updated_at >= ttl_cutoff
        self.assertTrue(reused2)

    def test_idempotency_external_message_id(self):
        db = self.Session()
        c = Conversation(channel='whatsapp', external_user_id='abc')
        db.add(c)
        db.flush()
        sid = 'SM123'
        m1 = Message(conversation_id=c.id, direction='inbound', text='hi', external_message_id=sid)
        db.add(m1)
        db.commit()

        # Duplicate sid should be considered existing
        dup = db.query(Message).filter(Message.external_message_id == sid).first()
        self.assertIsNotNone(dup)

        # Ensure only one message exists for that sid
        count = db.query(Message).filter(Message.external_message_id == sid).count()
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
