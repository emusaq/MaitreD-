from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.models import SessionLocal, Note


def add_note(
    client_id: int,
    note_text: str,
    history_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    db: Session = SessionLocal()
) -> int:
    """Create a new note. Returns the newly created note_id."""
    new_note = Note(
        client_id=client_id,
        history_id=history_id,
        employee_id=employee_id,
        note_text=note_text
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note.note_id


def get_note(note_id: int, db: Session = SessionLocal()) -> Optional[Note]:
    """Retrieve a single note by its primary key."""
    return db.get(Note, note_id)


def get_notes_by_client(client_id: int, db: Session = SessionLocal()) -> List[Note]:
    """Return every note that belongs to a given client."""
    return (
        db.query(Note)
        .filter_by(client_id=client_id)
        .order_by(Note.created_at.desc())
        .all()
    )


def get_notes_by_history(history_id: int, db: Session = SessionLocal()) -> List[Note]:
    """Return every note attached to a specific visit (history record)."""
    return (
        db.query(Note)
        .filter_by(history_id=history_id)
        .order_by(Note.created_at.desc())
        .all()
    )


def update_note(note_id: int, new_text: str, db: Session = SessionLocal()) -> bool:
    """Update the body of an existing note."""
    note = get_note(note_id, db)
    if note:
        note.note_text = new_text
        note.created_at = func.current_timestamp()
        db.commit()
        return True
    return False


def delete_note(note_id: int, db: Session = SessionLocal()) -> bool:
    """Remove a note permanently."""
    note = get_note(note_id, db)
    if note:
        db.delete(note)
        db.commit()
        return True
    return False
