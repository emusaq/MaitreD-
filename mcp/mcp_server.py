import re as _re
from pydantic import BaseModel, Field, validator
from webapp import app
from models.models import get_db, ReservationSettings

try:
    from agents.mcp import mcp_server_fastapi  # type: ignore
except Exception:
    # Fallback shim when agents.mcp is unavailable (e.g., tests)
    class _ShimServer:
        def __init__(self, *_args, **_kwargs):
            pass
        def tool(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
    def mcp_server_fastapi(*_args, **_kwargs):
        return _ShimServer()


from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from datetime import datetime, time
from models.models import Client
from sqlalchemy import text

_SLOT_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$')

server = mcp_server_fastapi(app, name="maitred-mcp")

ALLOWED_TOOLS = {"list_open_times", "check_availability", "create_reservation"}


class ListOpenTimesIn(BaseModel):
    date_iso: str = Field(..., description="Date in YYYY-MM-DD")
    party_size: int = Field(..., gt=0)

    @validator("date_iso")
    def _validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
        except Exception:
            raise ValueError("date_iso must be YYYY-MM-DD")
        return v


class CheckAvailabilityIn(BaseModel):
    date_iso: str
    time_24h: str  # HH:MM
    party_size: int = Field(..., gt=0)


class CreateReservationIn(BaseModel):
    slot_id: str
    party_size: int = Field(..., gt=0)
    # Opaque server-provided token only. No names/phones/emails allowed.
    client_ref: int | None = None


def _ensure_allowed(tool_name: str):
    if tool_name not in ALLOWED_TOOLS:
        raise HTTPException(status_code=403, detail="Tool not allowed")


def _get_settings(db: Session) -> ReservationSettings:
    """Return the active reservation settings row, or a default if none seeded."""
    settings = db.query(ReservationSettings).first()
    if settings is None:
        # Return an in-memory default so tools always have something to work with
        settings = ReservationSettings(
            reservations_enabled=True,
            open_from="17:00",
            open_to="21:00",
            slot_interval=30,
            max_per_slot=20,
            max_party_size=8,
        )
    return settings


def _generate_slots(date_iso: str, open_from: str, open_to: str, interval: int) -> list[dict]:
    """Generate slot dicts between open_from and open_to at `interval` minutes."""
    start = time.fromisoformat(open_from)
    end = time.fromisoformat(open_to)
    slots = []
    current = datetime.combine(datetime.fromisoformat(date_iso), start)
    end_dt = datetime.combine(datetime.fromisoformat(date_iso), end)
    from datetime import timedelta
    while current < end_dt:
        t = current.strftime("%H:%M")
        slots.append({"slot_id": f"{date_iso}_{t}", "time_24h": t})
        current += timedelta(minutes=interval)
    return slots


def _validate_slot_id(slot_id: str, settings: ReservationSettings) -> Optional[str]:
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


@server.tool(name="list_open_times", input_model=ListOpenTimesIn)
async def list_open_times(data: ListOpenTimesIn, db: Session = Depends(get_db)):
    _ensure_allowed("list_open_times")
    settings = _get_settings(db)

    if not settings.reservations_enabled:
        return {"date_iso": data.date_iso, "party_size": data.party_size, "slots": [], "message": "Reservations are currently not available."}

    if data.party_size > settings.max_party_size:
        return {"date_iso": data.date_iso, "party_size": data.party_size, "slots": [], "message": f"Maximum party size is {settings.max_party_size}."}

    all_slots = _generate_slots(data.date_iso, settings.open_from, settings.open_to, settings.slot_interval)

    # Filter out slots that have reached max_per_slot capacity
    open_slots = []
    for slot in all_slots:
        booked = db.execute(
            text("SELECT COALESCE(SUM(party_size), 0) FROM reservations WHERE slot_id = :slot"),
            {"slot": slot["slot_id"]}
        ).scalar()
        if (booked or 0) + data.party_size <= settings.max_per_slot:
            open_slots.append(slot)

    return {"date_iso": data.date_iso, "party_size": data.party_size, "slots": open_slots}


@server.tool(name="check_availability", input_model=CheckAvailabilityIn)
async def check_availability(data: CheckAvailabilityIn, db: Session = Depends(get_db)):
    _ensure_allowed("check_availability")
    settings = _get_settings(db)
    slot_id = f"{data.date_iso}_{data.time_24h}"

    if not settings.reservations_enabled:
        return {"slot_id": slot_id, "available": False, "reason": "reservations_disabled"}

    if data.party_size > settings.max_party_size:
        return {"slot_id": slot_id, "available": False, "reason": "party_too_large"}

    booked = db.execute(
        text("SELECT COALESCE(SUM(party_size), 0) FROM reservations WHERE slot_id = :slot"),
        {"slot": slot_id}
    ).scalar()
    available = (booked or 0) + data.party_size <= settings.max_per_slot
    return {"slot_id": slot_id, "available": available}


@server.tool(name="create_reservation", input_model=CreateReservationIn)
async def create_reservation(data: CreateReservationIn, db: Session = Depends(get_db)):
    _ensure_allowed("create_reservation")
    settings = _get_settings(db)

    if not settings.reservations_enabled:
        raise HTTPException(status_code=409, detail="Reservations are currently disabled.")

    if data.party_size > settings.max_party_size:
        raise HTTPException(status_code=422, detail=f"Maximum party size is {settings.max_party_size}.")

    slot_error = _validate_slot_id(data.slot_id, settings)
    if slot_error:
        raise HTTPException(status_code=422, detail=slot_error)

    # Server-side safeguard: only use opaque client_ref (id), never free-text PII
    client_id = None
    if data.client_ref is not None:
        client = db.get(Client, int(data.client_ref))
        if client:
            client_id = client.client_id

    date_iso, time_24h = data.slot_id.split("_", 1)

    # Atomic conditional INSERT: only inserts if the slot still has capacity.
    row = db.execute(
        text(
            "INSERT INTO reservations (date_iso, time_24h, party_size, slot_id, client_id) "
            "SELECT :date_iso, :time_24h, :party_size, :slot_id, :client_id "
            "WHERE COALESCE("
            "  (SELECT SUM(party_size) FROM reservations WHERE slot_id = :slot_id), 0"
            ") + :party_size <= :max_per_slot "
            "RETURNING id"
        ),
        {
            "date_iso": date_iso,
            "time_24h": time_24h,
            "party_size": data.party_size,
            "slot_id": data.slot_id,
            "client_id": client_id,
            "max_per_slot": settings.max_per_slot,
        },
    )
    new_id = row.scalar()
    db.commit()
    if new_id is None:
        raise HTTPException(status_code=409, detail="This time slot is fully booked.")
    # Return only opaque ids/times, never names/emails/phones
    return {"reservation_id": new_id, "slot_id": data.slot_id, "party_size": data.party_size}
