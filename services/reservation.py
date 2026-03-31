"""Consolidated reservation business logic.

Shared by the LLM path (reservation_tools.py) and the MCP path
(mcp/mcp_server.py). Both paths delegate to ReservationService; neither
duplicates slot generation, validation, or the atomic INSERT.

Hook registry allows post-reservation callbacks (Slack, AI summary, audit)
to be registered at startup without touching core booking logic.
"""
import re
from datetime import datetime, time, timedelta
from typing import Callable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.models import ReservationSettings
from utils import logger

_SLOT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$')

# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------

_on_reservation_created_hooks: List[Callable] = []


def register_reservation_hook(fn: Callable) -> None:
    """Register a callback invoked after a reservation is successfully created.

    Hook signature: fn(reservation_id: int, slot_id: str, db: Session) -> None
    Errors are caught and logged; they never block the booking response.
    """
    _on_reservation_created_hooks.append(fn)


def _fire_hooks(reservation_id: int, slot_id: str, db: Session) -> None:
    """Fire all registered post-reservation hooks. Errors are logged, never raised."""
    for hook in _on_reservation_created_hooks:
        try:
            hook(reservation_id, slot_id, db)
        except Exception as e:
            logger.error(f"reservation hook {hook.__name__} failed: {e}")


# ---------------------------------------------------------------------------
# ReservationService
# ---------------------------------------------------------------------------

class ReservationService:

    @staticmethod
    def get_settings(db: Session) -> ReservationSettings:
        """Return the active reservation settings row, or an in-memory default."""
        settings = db.query(ReservationSettings).first()
        if settings is None:
            settings = ReservationSettings(
                reservations_enabled=True,
                open_from=time(17, 0),
                open_to=time(21, 0),
                slot_interval=30,
                max_per_slot=20,
                max_party_size=8,
            )
        return settings

    @staticmethod
    def generate_slots(date_iso: str, open_from, open_to, interval: int) -> List[dict]:
        """Generate slot dicts between open_from and open_to at interval-minute steps."""
        start = open_from if isinstance(open_from, time) else time.fromisoformat(str(open_from))
        end = open_to if isinstance(open_to, time) else time.fromisoformat(str(open_to))
        slots = []
        current = datetime.combine(datetime.fromisoformat(date_iso), start)
        end_dt = datetime.combine(datetime.fromisoformat(date_iso), end)
        while current < end_dt:
            t = current.strftime("%H:%M")
            slots.append({"slot_id": f"{date_iso}_{t}", "time_24h": t})
            current += timedelta(minutes=interval)
        return slots

    @staticmethod
    def validate_slot_id(slot_id: str, settings: ReservationSettings) -> Optional[str]:
        """Return an error string if the slot_id is invalid, or None if valid."""
        if not _SLOT_RE.match(slot_id):
            return "Invalid slot_id format. Expected YYYY-MM-DD_HH:MM."
        date_part, time_part = slot_id.split("_", 1)
        try:
            datetime.fromisoformat(date_part)
        except ValueError:
            return "Invalid date in slot_id."
        try:
            slot_time = time.fromisoformat(time_part)
        except ValueError:
            return "Invalid time in slot_id."

        open_from = (
            settings.open_from
            if isinstance(settings.open_from, time)
            else time.fromisoformat(str(settings.open_from))
        )
        open_to = (
            settings.open_to
            if isinstance(settings.open_to, time)
            else time.fromisoformat(str(settings.open_to))
        )

        if not (open_from <= slot_time < open_to):
            return (
                f"Requested time {time_part} is outside business hours "
                f"({open_from.strftime('%H:%M')}–{open_to.strftime('%H:%M')})."
            )

        from_minutes = open_from.hour * 60 + open_from.minute
        slot_minutes = slot_time.hour * 60 + slot_time.minute
        if (slot_minutes - from_minutes) % settings.slot_interval != 0:
            return f"Requested time does not align to the {settings.slot_interval}-minute slot interval."

        return None

    @staticmethod
    def check_slot_capacity(
        slot_id: str, party_size: int, settings: ReservationSettings, db: Session
    ) -> bool:
        """Return True if the slot has remaining capacity for party_size guests."""
        booked = db.execute(
            text("SELECT COALESCE(SUM(party_size), 0) FROM reservations WHERE slot_id = :s"),
            {"s": slot_id},
        ).scalar() or 0
        return booked + party_size <= settings.max_per_slot

    @staticmethod
    def list_open_times(date_iso: str, party_size: int, db: Session) -> dict:
        settings = ReservationService.get_settings(db)
        if not settings.reservations_enabled:
            return {"slots": [], "message": "Reservations are currently not available."}
        if party_size > settings.max_party_size:
            return {"slots": [], "message": f"Maximum party size is {settings.max_party_size}."}

        all_slots = ReservationService.generate_slots(
            date_iso, settings.open_from, settings.open_to, settings.slot_interval
        )
        open_slots = [
            slot for slot in all_slots
            if ReservationService.check_slot_capacity(slot["slot_id"], party_size, settings, db)
        ]
        return {"date_iso": date_iso, "party_size": party_size, "slots": open_slots}

    @staticmethod
    def check_availability(date_iso: str, time_24h: str, party_size: int, db: Session) -> dict:
        settings = ReservationService.get_settings(db)
        slot_id = f"{date_iso}_{time_24h}"
        if not settings.reservations_enabled:
            return {"slot_id": slot_id, "available": False, "reason": "reservations_disabled"}
        if party_size > settings.max_party_size:
            return {"slot_id": slot_id, "available": False, "reason": "party_too_large"}
        available = ReservationService.check_slot_capacity(slot_id, party_size, settings, db)
        return {"slot_id": slot_id, "available": available}

    @staticmethod
    def create_reservation(
        slot_id: str,
        party_size: int,
        db: Session,
        guest_name: str = "",
        occasion: str = "",
        client_id: Optional[int] = None,
    ) -> dict:
        """Attempt to create a reservation using an atomic conditional INSERT.

        Returns a dict with `reservation_id` on success, or `error` on failure.
        The caller is responsible for firing hooks after a successful create.
        """
        settings = ReservationService.get_settings(db)
        if not settings.reservations_enabled:
            return {"error": "Reservations are currently disabled."}
        if party_size > settings.max_party_size:
            return {"error": f"Maximum party size is {settings.max_party_size}."}

        slot_error = ReservationService.validate_slot_id(slot_id, settings)
        if slot_error:
            return {"error": slot_error}

        date_iso, time_24h = slot_id.split("_", 1)

        # Atomic conditional INSERT: only inserts if the slot still has capacity.
        # Closes the read-check-insert race for single-process deployments.
        row = db.execute(
            text(
                "INSERT INTO reservations "
                "  (date_iso, time_24h, party_size, slot_id, status, guest_name, occasion, client_id) "
                "SELECT :date_iso, :time_24h, :party_size, :slot_id, 'pending', "
                "       :guest_name, :occasion, :client_id "
                "WHERE COALESCE("
                "  (SELECT SUM(party_size) FROM reservations WHERE slot_id = :slot_id), 0"
                ") + :party_size <= :max_per_slot "
                "RETURNING id"
            ),
            {
                "date_iso": date_iso,
                "time_24h": time_24h,
                "party_size": party_size,
                "slot_id": slot_id,
                "guest_name": guest_name,
                "occasion": occasion,
                "client_id": client_id,
                "max_per_slot": settings.max_per_slot,
            },
        )
        new_id = row.scalar()  # read BEFORE commit — cursor closed after commit
        db.commit()
        if new_id is None:
            return {"error": "This time slot is fully booked."}
        return {"reservation_id": new_id, "slot_id": slot_id, "party_size": party_size, "status": "pending"}
