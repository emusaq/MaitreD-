from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.models import SessionLocal, Note


def add_note(
    client_id: int,
    note_text: str,
    history_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> int:
    """Create a new note. Returns the newly created note_id."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
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
    finally:
        if _close:
            db.close()


def get_note(note_id: int, db: Optional[Session] = None) -> Optional[Note]:
    """Retrieve a single note by its primary key."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return db.get(Note, note_id)
    finally:
        if _close:
            db.close()


def get_notes_by_client(client_id: int, db: Optional[Session] = None) -> List[Note]:
    """Return every note that belongs to a given client."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return (
            db.query(Note)
            .filter_by(client_id=client_id)
            .order_by(Note.created_at.desc())
            .all()
        )
    finally:
        if _close:
            db.close()


def get_notes_by_history(history_id: int, db: Optional[Session] = None) -> List[Note]:
    """Return every note attached to a specific visit (history record)."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return (
            db.query(Note)
            .filter_by(history_id=history_id)
            .order_by(Note.created_at.desc())
            .all()
        )
    finally:
        if _close:
            db.close()


def update_note(note_id: int, new_text: str, db: Optional[Session] = None) -> bool:
    """Update the body of an existing note."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        note = get_note(note_id, db)
        if note:
            note.note_text = new_text
            note.created_at = func.current_timestamp()
            db.commit()
            return True
        return False
    finally:
        if _close:
            db.close()


def delete_note(note_id: int, db: Optional[Session] = None) -> bool:
    """Remove a note permanently."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        note = get_note(note_id, db)
        if note:
            db.delete(note)
            db.commit()
            return True
        return False
    finally:
        if _close:
            db.close()
