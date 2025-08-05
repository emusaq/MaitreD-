from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.models import SessionLocal, Client


def list_clients(db: Session = SessionLocal()) -> List[Client]:
    """Return a list of all clients."""
    return db.query(Client).order_by(Client.last_name, Client.first_name).all()


def get_client_by_id(client_id: int, db: Session = SessionLocal()) -> Optional[Client]:
    """Return client by id."""
    return db.get(Client, client_id)


def get_client_by_name(
    first_name: str, last_name: str, db: Session = SessionLocal()
) -> Optional[Client]:
    """Return a client row by first and last name."""
    return (
        db.query(Client)
        .filter_by(first_name=first_name, last_name=last_name)
        .first()
    )


def get_client_by_phone(phone_number: str, db: Session = SessionLocal()) -> Optional[Client]:
    """Return client row by phone number."""
    return db.query(Client).filter_by(phone_number=phone_number).first()


def create_client(
    first_name: str,
    last_name: str,
    phone_number: str,
    email: Optional[str] = None,
    birthday: Optional[str] = None,
    preferred_seating: Optional[str] = None,
    preferred_server: Optional[str] = None,
    preferred_communication: Optional[str] = None,
    allow_marketing: bool = True,
    db: Session = SessionLocal()
) -> int:
    """Create a client and return their client_id."""
    new_client = Client(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        email=email,
        birthday=birthday,
        preferred_seating=preferred_seating,
        preferred_server=preferred_server,
        preferred_communication=preferred_communication,
        allow_marketing=allow_marketing,
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return new_client.client_id


def update_client_summary(
    client_id: int, summary: str, db: Session = SessionLocal()
) -> bool:
    """Update the summary note for a client."""
    client = get_client_by_id(client_id, db)
    if client:
        client.client_summary = summary
        db.commit()
        return True
    return False


def update_last_visit(client_id: int, db: Session = SessionLocal()) -> bool:
    """Update the last visit to current timestamp."""
    client = get_client_by_id(client_id, db)
    if client:
        client.last_visit = func.current_timestamp()
        db.commit()
        return True
    return False
