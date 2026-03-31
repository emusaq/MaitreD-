from sqlalchemy import create_engine, Column, Integer, String, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Text, Date, DateTime, Time, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship

from config import get_database_url

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)
    external_user_id = Column(String, index=True)
    opened_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp())
    status = Column(String, default="open")

    # Relationship to messages
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String, nullable=False)  # 'inbound' | 'outbound'
    text = Column(Text, nullable=False)
    external_message_id = Column(String, unique=False, index=False)
    created_at = Column(DateTime, default=func.current_timestamp())

    conversation = relationship("Conversation", back_populates="messages")

# Partial unique index: enforces idempotency on non-NULL external_message_id
_idx_messages_external_id = Index(
    "idx_messages_external_id",
    Message.external_message_id,
    unique=True,
    postgresql_where=(Message.external_message_id.isnot(None)),
)


## ORM models based on raw schema for Clients, Restaurants, Employees, History, and Notes

# Client model
class Client(Base):
    __tablename__ = "clients"

    client_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    phone_number = Column(Text, unique=True, nullable=False)
    email = Column(Text, unique=True)
    client_summary = Column(Text)
    ai_summary = Column(Text)
    birthday = Column(Date)
    preferred_seating = Column(Text)
    preferred_server = Column(Text)
    preferred_communication = Column(Text)
    last_visit = Column(DateTime)
    allow_marketing = Column(Boolean, default=True)
    date_created = Column(Date, default=func.current_date())

    histories = relationship("History", back_populates="client")
    notes = relationship("Note", back_populates="client")

# Restaurant model
class Restaurant(Base):
    __tablename__ = "restaurants"

    restaurant_id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    location = Column(Text)

    histories = relationship("History", back_populates="restaurant")

# Employee model
class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    access_code = Column(Integer, nullable=False)
    username = Column(Text, unique=True)
    password = Column(Text)

    histories = relationship("History", back_populates="employee")
    notes = relationship("Note", back_populates="employee")

# History model
class History(Base):
    __tablename__ = "history"

    history_id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.restaurant_id", ondelete="SET NULL"))
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="SET NULL"))
    items_ordered = Column(Text)
    visit_date = Column(DateTime, default=func.current_timestamp())

    client = relationship("Client", back_populates="histories")
    restaurant = relationship("Restaurant", back_populates="histories")
    employee = relationship("Employee", back_populates="histories")
    notes = relationship("Note", back_populates="history")

# Note model
class Note(Base):
    __tablename__ = "notes"

    note_id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=False)
    history_id = Column(Integer, ForeignKey("history.history_id"), index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="SET NULL"))
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.current_timestamp())

    client = relationship("Client", back_populates="notes")
    history = relationship("History", back_populates="notes")
    employee = relationship("Employee", back_populates="notes")

# Reservation model
class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    date_iso = Column(Date, nullable=False)
    time_24h = Column(Time, nullable=False)
    party_size = Column(Integer, nullable=False)
    slot_id = Column(Text, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.client_id"))
    status = Column(Text, nullable=False, default="pending", server_default="'pending'")
    guest_name = Column(Text)
    occasion = Column(Text)
    guest_phone = Column(Text)
    note = Column(Text)
    note_author = Column(Text)

    client = relationship("Client")

# Reservation settings (staff-controlled)
class ReservationSettings(Base):
    __tablename__ = "reservation_settings"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.restaurant_id"))
    reservations_enabled = Column(Boolean, nullable=False, default=True)
    open_from = Column(Time, nullable=False, default="17:00")
    open_to = Column(Time, nullable=False, default="21:00")
    slot_interval = Column(Integer, nullable=False, default=30)
    max_per_slot = Column(Integer, nullable=False, default=20)
    max_party_size = Column(Integer, nullable=False, default=8)
    large_party_threshold = Column(Integer, nullable=False, default=8)
    large_party_phone = Column(Text, nullable=False, default="")
    confirm_message = Column(Text, nullable=False, default="Your reservation at Garufa has been confirmed. We look forward to welcoming you.")
    deny_message = Column(Text, nullable=False, default="We regret we are unable to accommodate your request at this time. Please contact us directly for assistance.")
    cancel_message = Column(Text, nullable=False, default="Your reservation at Garufa has been cancelled. We apologize for any inconvenience.")
    chatbot_paused = Column(Boolean, nullable=False, default=False)
    paused_away_message = Column(Text, nullable=False, default="We are temporarily unavailable. Please contact us directly or try again later.")
    updated_at = Column(DateTime, default=func.current_timestamp())
    updated_by = Column(Integer, ForeignKey("employees.employee_id"))


import os as _os
if _os.getenv("SQLALCHEMY_CREATE_ALL", "0") == "1":
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
