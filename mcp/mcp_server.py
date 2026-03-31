"""MCP server tools for the reservation flow.

webapp.py calls init_server(app) after creating the FastAPI app, so this
module can be imported without triggering webapp.py initialization — no
circular import risk, and tests can import tools directly.
"""
from pydantic import BaseModel, Field, field_validator
from models.models import get_db, ReservationSettings
from services.reservation import ReservationService

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
from datetime import datetime

server = None

ALLOWED_TOOLS = {"list_open_times", "check_availability", "create_reservation"}


class ListOpenTimesIn(BaseModel):
    date_iso: str = Field(..., description="Date in YYYY-MM-DD")
    party_size: int = Field(..., gt=0)

    @field_validator("date_iso")
    @classmethod
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
    client_ref: Optional[int] = None


def _ensure_allowed(tool_name: str):
    if tool_name not in ALLOWED_TOOLS:
        raise HTTPException(status_code=403, detail="Tool not allowed")


# ---------------------------------------------------------------------------
# Tool implementations (importable without server being initialized)
# ---------------------------------------------------------------------------

async def list_open_times(data: ListOpenTimesIn, db: Session = Depends(get_db)):
    _ensure_allowed("list_open_times")
    result = ReservationService.list_open_times(data.date_iso, data.party_size, db)
    return {"date_iso": data.date_iso, "party_size": data.party_size, **result}


async def check_availability(data: CheckAvailabilityIn, db: Session = Depends(get_db)):
    _ensure_allowed("check_availability")
    return ReservationService.check_availability(data.date_iso, data.time_24h, data.party_size, db)


async def create_reservation(data: CreateReservationIn, db: Session = Depends(get_db)):
    _ensure_allowed("create_reservation")

    # Resolve opaque client_ref to a DB client_id (never accept free-text PII)
    client_id = None
    if data.client_ref is not None:
        from models.models import Client
        client = db.get(Client, int(data.client_ref))
        if client:
            client_id = client.client_id

    result = ReservationService.create_reservation(
        data.slot_id, data.party_size, db, client_id=client_id
    )

    if "error" in result:
        # Map service errors to appropriate HTTP status codes
        detail = result["error"]
        if "disabled" in detail or "fully booked" in detail:
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=422, detail=detail)

    # Return only opaque ids/times, never names/emails/phones
    return {"reservation_id": result["reservation_id"], "slot_id": result["slot_id"], "party_size": result["party_size"]}


# Re-export for backwards compatibility (e.g. tests that do
# `from mcp.mcp_server import _validate_slot_id`)
_validate_slot_id = ReservationService.validate_slot_id


# ---------------------------------------------------------------------------
# Server initialization — called from webapp.py after app = FastAPI()
# ---------------------------------------------------------------------------

def init_server(app):
    """Register MCP tools with the FastAPI app. Must be called once at startup."""
    global server
    server = mcp_server_fastapi(app, name="maitred-mcp")
    server.tool(name="list_open_times", input_model=ListOpenTimesIn)(list_open_times)
    server.tool(name="check_availability", input_model=CheckAvailabilityIn)(check_availability)
    server.tool(name="create_reservation", input_model=CreateReservationIn)(create_reservation)
    return server
