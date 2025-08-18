from pydantic import BaseModel, root_validator
from manage import app, get_db
from agents.mcp import mcp_server_fastapi
from sqlalchemy.orm import Session
from fastapi import Depends

from models import client as client_model
from models import reservations as reservation_model

server = mcp_server_fastapi(app, name="maitred-mcp")

class UpsertReservationIn(BaseModel):
    date: str
    time: str
    covers: int
    # Either an existing client_id OR a client_name for new/unknown clients
    client_id: int | None = None
    client_name: str | None = None
    special_requests: str | None = None
    occasion: str | None = None
    seating: str | None = None
    dietary: str | None = None
    source: str | None = None
    language_guess: str | None = None
    parsed_party_size: int | None = None
    parsed_date: str | None = None
    parsed_time: str | None = None
    created_by_bot: bool = False

    @root_validator
    def client_reference_required(cls, values):
        if not values.get("client_id") and not values.get("client_name"):
            raise ValueError("Provide either client_id or client_name")
        return values

@server.tool(
    name="upsert_reservation",
    description=(
        "Create or modify a reservation. "
        "Use client_id for existing clients or client_name to create/find a new client."
    ),
    input_model=UpsertReservationIn
)
async def upsert_reservation(
    data: UpsertReservationIn,
    db: Session = Depends(get_db),
):
    # Resolve or create client when only a name is supplied
    if data.client_id is None:
        data.client_id = client_model.get_or_create_client_id(data.client_name)

    payload = data.dict(exclude={"client_name"})
    return reservation_model.upsert_reservation(**payload)