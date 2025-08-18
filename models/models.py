from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker
from decouple import config
from sqlalchemy import Text, Date, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship

#connection to maitred postgresql database
url = URL.create(
    drivername ="postgresql",
    username=config("DB_USER"),
    password=config("DB_PASSWORD"),
    host="localhost",
    database="maitred",
    port=5433
)

engine = create_engine(url)
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
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    direction = Column(String, nullable=False)  # 'inbound' | 'outbound'
    text = Column(Text, nullable=False)
    external_message_id = Column(String, unique=False, index=True)
    created_at = Column(DateTime, default=func.current_timestamp())

    conversation = relationship("Conversation", back_populates="messages")


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
    client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.restaurant_id"))
    employee_id = Column(Integer, ForeignKey("employees.employee_id"))
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
    client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False)
    history_id = Column(Integer, ForeignKey("history.history_id"))
    employee_id = Column(Integer, ForeignKey("employees.employee_id"))
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.current_timestamp())

    client = relationship("Client", back_populates="notes")
    history = relationship("History", back_populates="notes")
    employee = relationship("Employee", back_populates="notes")

import os as _os
if _os.getenv("SQLALCHEMY_CREATE_ALL", "1") == "1":
    Base.metadata.create_all(engine)
