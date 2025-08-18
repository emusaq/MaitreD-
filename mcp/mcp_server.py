from pydantic import BaseModel, Field, validator
from manage import app, get_db
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
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from models.models import SessionLocal
from sqlalchemy import and_
from datetime import datetime, time as dtime

from models.models import Client
from sqlalchemy import text

server = mcp_server_fastapi(app, name="maitred-mcp")

ALLOWED_TOOLS = {"list_open_times", "check_availability", "create_reservation"}


class ListOpenTimesIn(BaseModel):
    date_iso: str = Field(..., description="Date in YYYY-MM-DD")
    party_size: int = Field(..., gt=0)

    @validator("date_iso")
    def _validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
        except Exception as _:
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


@server.tool(name="list_open_times", input_model=ListOpenTimesIn)
async def list_open_times(data: ListOpenTimesIn, db: Session = Depends(get_db)):
    _ensure_allowed("list_open_times")
    # Simple fixed window: every 30 minutes between 17:00 and 21:00 local
    slots = []
    for h in range(17, 21):
        for m in (0, 30):
            t = f"{h:02d}:{m:02d}"
            slots.append({"slot_id": f"{data.date_iso}_{t}", "time_24h": t})
    # Do not return any PII
    return {"date_iso": data.date_iso, "party_size": data.party_size, "slots": slots}


@server.tool(name="check_availability", input_model=CheckAvailabilityIn)
async def check_availability(data: CheckAvailabilityIn, db: Session = Depends(get_db)):
    _ensure_allowed("check_availability")
    slot_id = f"{data.date_iso}_{data.time_24h}"
    row = db.execute(text("SELECT 1 FROM reservations WHERE slot_id = :slot"), {"slot": slot_id}).fetchone()
    available = row is None
    return {"slot_id": slot_id, "available": available}


@server.tool(name="create_reservation", input_model=CreateReservationIn)
async def create_reservation(data: CreateReservationIn, db: Session = Depends(get_db)):
    _ensure_allowed("create_reservation")
    # Server-side safeguard: only use opaque client_ref (id), never free-text PII
    client_id = None
    if data.client_ref is not None:
        # Only accept integer ids that exist; do not expose any PII
        client = db.get(Client, int(data.client_ref))
        if client:
            client_id = client.client_id

    date_iso, time_24h = data.slot_id.split("_", 1)
    db.execute(
        text(
            """
            INSERT INTO reservations (date_iso, time_24h, party_size, slot_id, client_id)
            VALUES (:date_iso, :time_24h, :party_size, :slot_id, :client_id)
            """
        ),
        {
            "date_iso": date_iso,
            "time_24h": time_24h,
            "party_size": data.party_size,
            "slot_id": data.slot_id,
            "client_id": client_id,
        },
    )
    db.commit()
    # Return only opaque ids/times, never names/emails/phones
    return {"reservation_id": data.slot_id, "slot_id": data.slot_id, "party_size": data.party_size}
