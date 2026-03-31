"""ORM-based CRUD for the reservations table.

Replaces the inline db.execute(text(...)) calls scattered across staff/app.py
and webapp.py with named, typed functions.
"""
from datetime import date
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models.models import Reservation, Client


def _parse_date(date_iso: str) -> date:
    return date.fromisoformat(date_iso)


def get_reservations_for_date(date_iso: str, db: Session) -> List:
    """Return reservation rows (with optional client join) for a given date."""
    stmt = (
        select(
            Reservation.id,
            Reservation.slot_id,
            Reservation.date_iso,
            Reservation.time_24h,
            Reservation.party_size,
            Reservation.note,
            Client.first_name,
            Client.last_name,
            Reservation.status,
            Reservation.guest_name,
            Reservation.occasion,
        )
        .outerjoin(Client, Client.client_id == Reservation.client_id)
        .where(Reservation.date_iso == _parse_date(date_iso))
        .order_by(Reservation.time_24h)
    )
    return db.execute(stmt).fetchall()


def get_reservations_for_date_simple(date_iso: str, db: Session) -> List:
    """Return reservation rows (dashboard view: fewer columns) for a given date."""
    stmt = (
        select(
            Reservation.id,
            Reservation.slot_id,
            Reservation.time_24h,
            Reservation.party_size,
            Client.first_name,
            Client.last_name,
            Reservation.status,
            Reservation.guest_name,
        )
        .outerjoin(Client, Client.client_id == Reservation.client_id)
        .where(Reservation.date_iso == _parse_date(date_iso))
        .order_by(Reservation.time_24h)
    )
    return db.execute(stmt).fetchall()


def get_reservation_by_id(reservation_id: int, db: Session) -> Optional[Reservation]:
    """Return a single Reservation ORM object by primary key."""
    return db.get(Reservation, reservation_id)


def update_reservation_status(reservation_id: int, status: str, db: Session) -> None:
    """Update the status column for a reservation and commit."""
    db.execute(
        text("UPDATE reservations SET status = :status WHERE id = :id"),
        {"status": status, "id": reservation_id},
    )
    db.commit()


def get_reservation_guest_phone(reservation_id: int, db: Session) -> Optional[str]:
    """Return the guest_phone for a reservation, or None if not found."""
    row = db.execute(
        text("SELECT guest_phone FROM reservations WHERE id = :id"),
        {"id": reservation_id},
    ).fetchone()
    return row[0] if row is not None else None


def attach_guest_phone(reservation_id: int, phone: str, db: Session) -> None:
    """Store the guest's WhatsApp phone number on a reservation and commit."""
    db.execute(
        text("UPDATE reservations SET guest_phone = :phone WHERE id = :id"),
        {"phone": phone, "id": reservation_id},
    )
    db.commit()
