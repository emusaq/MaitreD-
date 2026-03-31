from typing import List, Optional
from sqlalchemy.orm import Session, joinedload

from models.models import SessionLocal, History, Note


def get_client_history(
    client_id: int, db: Optional[Session] = None
) -> List[History]:
    """Return history records for a client, including related notes."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return (
            db.query(History)
            .options(joinedload(History.notes))
            .filter_by(client_id=client_id)
            .order_by(History.visit_date.desc())
            .all()
        )
    finally:
        if _close:
            db.close()


def add_visit(
    client_id: int,
    employee_id: Optional[int],
    items_ordered: str,
    note_text: Optional[str] = None,
    db: Optional[Session] = None,
) -> int:
    """Add a visit record and optional note, returning the history_id."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        new_visit = History(
            client_id=client_id,
            employee_id=employee_id,
            items_ordered=items_ordered
        )
        db.add(new_visit)
        db.commit()
        db.refresh(new_visit)
        if note_text:
            new_note = Note(
                client_id=client_id,
                history_id=new_visit.history_id,
                employee_id=employee_id,
                note_text=note_text
            )
            db.add(new_note)
            db.commit()
        return new_visit.history_id
    finally:
        if _close:
            db.close()
