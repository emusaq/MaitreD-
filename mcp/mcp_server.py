from pydantic import BaseModel, root_validator
from manage import app, get_db
from agents.mcp import mcp_server_fastapi
from sqlalchemy.orm import Session
from fastapi import Depends
import models

server = mcp_server_fastapi(app, name="maitred-mcp")

class UpsertReservationIn(BaseModel):
    date: str
    time: str
    covers: int
    # Either an existing client_id OR a client_name for new/unknown clients
    client_id: int | None = None
    client_name: str | None = None
    special_request: str | None = None

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
        data.client_id = models.get_or_create_client_id(db, data.client_name)

    payload = data.dict(exclude={"client_name"})
    return models.upsert_reservation(db=db, **payload)