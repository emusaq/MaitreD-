"""
OpenAI function-calling definitions and execution logic for reservations.

This bridges the LLM conversation (webapp.py) with the actual database.
The tool logic mirrors mcp/mcp_server.py but runs synchronously inside
the /message request, so the model can actually create reservations.
"""
import json
import re
from datetime import datetime, time, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from models.models import ReservationSettings
from utils import logger

_SLOT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$')

# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_open_times",
            "description": (
                "List available reservation time slots for a given date and party size. "
                "Call this before confirming a time to show the guest their options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_iso": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format."
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                        "minimum": 1
                    }
                },
                "required": ["date_iso", "party_size"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check whether a specific time slot is available for a given party size."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_iso": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format."
                    },
                    "time_24h": {
                        "type": "string",
                        "description": "Time in HH:MM 24-hour format, e.g. '19:00'."
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                        "minimum": 1
                    }
                },
                "required": ["date_iso", "time_24h", "party_size"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": (
                "Submit a reservation request. Only call this after the guest has confirmed "
                "their name, occasion, date, time, and party size. "
                "The slot_id must come from list_open_times or be in format YYYY-MM-DD_HH:MM. "
                "Reservations are submitted as pending requests — the guest will be notified once confirmed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot_id": {
                        "type": "string",
                        "description": "Slot identifier in format YYYY-MM-DD_HH:MM, e.g. '2025-01-15_19:00'."
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                        "minimum": 1
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "The name for the reservation, as provided by the guest."
                    },
                    "occasion": {
                        "type": "string",
                        "description": "The occasion being celebrated (e.g. 'birthday', 'anniversary', 'business dinner'). Use 'none' if no occasion."
                    }
                },
                "required": ["slot_id", "party_size", "guest_name", "occasion"]
            }
        }
    }
]


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def _get_settings(db: Session) -> ReservationSettings:
    settings = db.query(ReservationSettings).first()
    if settings is None:
        settings = ReservationSettings(
            reservations_enabled=True,
            open_from="17:00",
            open_to="21:00",
            slot_interval=30,
            max_per_slot=20,
            max_party_size=8,
        )
    return settings


def _generate_slots(date_iso: str, open_from, open_to, interval: int) -> list[dict]:
    # open_from/open_to may be str ("17:00") or datetime.time depending on ORM/driver
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


def _validate_slot_id(slot_id: str, settings: ReservationSettings) -> Optional[str]:
    """Return an error string if the slot_id is invalid, or None if it is valid."""
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

    open_from = settings.open_from if isinstance(settings.open_from, time) else time.fromisoformat(str(settings.open_from))
    open_to = settings.open_to if isinstance(settings.open_to, time) else time.fromisoformat(str(settings.open_to))

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


def _run_list_open_times(date_iso: str, party_size: int, db: Session) -> dict:
    settings = _get_settings(db)
    if not settings.reservations_enabled:
        return {"slots": [], "message": "Reservations are currently not available."}
    if party_size > settings.max_party_size:
        return {"slots": [], "message": f"Maximum party size is {settings.max_party_size}."}

    all_slots = _generate_slots(date_iso, settings.open_from, settings.open_to, settings.slot_interval)
    open_slots = []
    for slot in all_slots:
        booked = db.execute(
            text("SELECT COALESCE(SUM(party_size), 0) FROM reservations WHERE slot_id = :s"),
            {"s": slot["slot_id"]}
        ).scalar() or 0
        if booked + party_size <= settings.max_per_slot:
            open_slots.append(slot)

    return {"date_iso": date_iso, "party_size": party_size, "slots": open_slots}


def _run_check_availability(date_iso: str, time_24h: str, party_size: int, db: Session) -> dict:
    settings = _get_settings(db)
    slot_id = f"{date_iso}_{time_24h}"
    if not settings.reservations_enabled:
        return {"slot_id": slot_id, "available": False, "reason": "reservations_disabled"}
    if party_size > settings.max_party_size:
        return {"slot_id": slot_id, "available": False, "reason": "party_too_large"}
    booked = db.execute(
        text("SELECT COALESCE(SUM(party_size), 0) FROM reservations WHERE slot_id = :s"),
        {"s": slot_id}
    ).scalar() or 0
    return {"slot_id": slot_id, "available": booked + party_size <= settings.max_per_slot}


def _run_create_reservation(slot_id: str, party_size: int, db: Session,
                             guest_name: str = "", occasion: str = "") -> dict:
    settings = _get_settings(db)
    if not settings.reservations_enabled:
        return {"error": "Reservations are currently disabled."}
    if party_size > settings.max_party_size:
        return {"error": f"Maximum party size is {settings.max_party_size}."}

    slot_error = _validate_slot_id(slot_id, settings)
    if slot_error:
        return {"error": slot_error}

    date_iso, time_24h = slot_id.split("_", 1)

    # Atomic conditional INSERT: only inserts if the slot still has capacity.
    # The WHERE sub-select and the INSERT execute as a single statement, closing
    # the read-check-insert race window under normal single-process load.
    row = db.execute(
        text(
            "INSERT INTO reservations (date_iso, time_24h, party_size, slot_id, status, guest_name, occasion) "
            "SELECT :date_iso, :time_24h, :party_size, :slot_id, 'pending', :guest_name, :occasion "
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
            "max_per_slot": settings.max_per_slot,
        },
    )
    new_id = row.scalar()  # read BEFORE commit — cursor is closed after commit
    db.commit()
    if new_id is None:
        return {"error": "This time slot is fully booked."}
    return {"reservation_id": new_id, "slot_id": slot_id, "party_size": party_size, "status": "pending"}


# ---------------------------------------------------------------------------
# Dispatcher — called from webapp.py
# ---------------------------------------------------------------------------

def execute_tool(tool_name: str, arguments: str, db: Session) -> str:
    """Parse OpenAI tool call arguments and run the matching function. Returns JSON string."""
    try:
        args = json.loads(arguments)
    except Exception:
        return json.dumps({"error": "Invalid arguments."})

    try:
        if tool_name == "list_open_times":
            result = _run_list_open_times(args["date_iso"], args["party_size"], db)
        elif tool_name == "check_availability":
            result = _run_check_availability(args["date_iso"], args["time_24h"], args["party_size"], db)
        elif tool_name == "create_reservation":
            result = _run_create_reservation(
                args["slot_id"], args["party_size"], db,
                guest_name=args.get("guest_name", ""),
                occasion=args.get("occasion", "none"),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as exc:
        logger.error(f"[tool={tool_name}] unhandled exception: {exc}", exc_info=True)
        db.rollback()  # Reset session so the rest of the request can still use it
        result = {"error": "Reservation system temporarily unavailable. Please try again."}

    return json.dumps(result)
