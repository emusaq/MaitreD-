"""Front-of-house staff webapp router."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from models.models import get_db, ReservationSettings, Client
from utils import send_message, logger
from staff.auth import (
    get_current_employee,
    require_manager,
    create_session_cookie,
    authenticate,
    COOKIE_NAME,
)
from sqlalchemy import text

import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)

router = APIRouter(prefix="/staff")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
):
    employee = authenticate(username, password)
    if employee is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=401,
        )
    token = create_session_cookie(employee.employee_id, employee.role)
    response = RedirectResponse(url="/staff/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set True in production (HTTPS)
        max_age=60 * 60 * 8,
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/staff/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    today = date.today().isoformat()
    rows = db.execute(
        text("""
            SELECT r.id, r.slot_id, r.time_24h::text, r.party_size,
                   c.first_name, c.last_name, r.status, r.guest_name
            FROM reservations r
            LEFT JOIN clients c ON c.client_id = r.client_id
            WHERE r.date_iso = :today
            ORDER BY r.time_24h
        """),
        {"today": today},
    ).fetchall()

    reservations = [
        {
            "id": row[0],
            "slot_id": row[1],
            "time_24h": row[2],
            "party_size": row[3],
            "client_name": f"{row[4]} {row[5]}" if row[4] else (row[7] or "Walk-in"),
            "status": row[6] or "pending",
            "guest_name": row[7],
        }
        for row in rows
    ]
    total_covers = sum(r["party_size"] for r in reservations)

    settings = db.query(ReservationSettings).first()
    reservations_enabled = settings.reservations_enabled if settings else True

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today": today,
            "reservations": reservations,
            "total_covers": total_covers,
            "reservations_enabled": reservations_enabled,
            "settings": settings,
            "session": session,
        },
    )


# ---------------------------------------------------------------------------
# Reservation list (date-filtered)
# ---------------------------------------------------------------------------

@router.get("/reservations", response_class=HTMLResponse)
async def reservation_list(
    request: Request,
    date_filter: Optional[str] = None,
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    target_date = date_filter or date.today().isoformat()
    rows = db.execute(
        text("""
            SELECT r.id, r.slot_id, r.date_iso::text, r.time_24h::text, r.party_size,
                   r.note, c.first_name, c.last_name, r.status, r.guest_name, r.occasion
            FROM reservations r
            LEFT JOIN clients c ON c.client_id = r.client_id
            WHERE r.date_iso = :d
            ORDER BY r.time_24h
        """),
        {"d": target_date},
    ).fetchall()

    reservations = [
        {
            "id": row[0],
            "slot_id": row[1],
            "date_iso": row[2],
            "time_24h": row[3],
            "party_size": row[4],
            "note": row[5],
            "client_name": f"{row[6]} {row[7]}" if row[6] else (row[9] or "Walk-in"),
            "status": row[8] or "pending",
            "guest_name": row[9],
            "occasion": row[10],
        }
        for row in rows
    ]

    settings_row = db.query(ReservationSettings).first()
    deny_message = settings_row.deny_message if settings_row else ""
    cancel_message = settings_row.cancel_message if settings_row else ""

    return templates.TemplateResponse(
        "reservations.html",
        {
            "request": request,
            "reservations": reservations,
            "date_filter": target_date,
            "deny_message": deny_message,
            "cancel_message": cancel_message,
            "session": session,
        },
    )


@router.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT guest_phone FROM reservations WHERE id = :id"),
        {"id": reservation_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    db.execute(
        text("UPDATE reservations SET status = 'confirmed' WHERE id = :id"),
        {"id": reservation_id},
    )
    db.commit()

    settings_row = db.query(ReservationSettings).first()
    confirm_msg = settings_row.confirm_message if settings_row else "Your reservation at Garufa has been confirmed. We look forward to welcoming you."
    guest_phone = row[0]
    if guest_phone:
        sid = send_message(guest_phone, confirm_msg)
        if sid is None:
            logger.warning(f"confirm_reservation id={reservation_id}: notification send failed (no SID returned)")

    return RedirectResponse(url="/staff/reservations", status_code=303)


@router.post("/reservations/{reservation_id}/deny")
async def deny_reservation(
    reservation_id: int,
    custom_message: str = Form(default=""),
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT guest_phone FROM reservations WHERE id = :id"),
        {"id": reservation_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    db.execute(
        text("UPDATE reservations SET status = 'denied' WHERE id = :id"),
        {"id": reservation_id},
    )
    db.commit()

    guest_phone = row[0]
    if guest_phone and custom_message.strip():
        sid = send_message(guest_phone, custom_message.strip())
        if sid is None:
            logger.warning(f"deny_reservation id={reservation_id}: notification send failed (no SID returned)")

    return RedirectResponse(url="/staff/reservations", status_code=303)


@router.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    custom_message: str = Form(default=""),
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT guest_phone FROM reservations WHERE id = :id"),
        {"id": reservation_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    db.execute(
        text("UPDATE reservations SET status = 'cancelled' WHERE id = :id"),
        {"id": reservation_id},
    )
    db.commit()

    guest_phone = row[0]
    if guest_phone and custom_message.strip():
        sid = send_message(guest_phone, custom_message.strip())
        if sid is None:
            logger.warning(f"cancel_reservation id={reservation_id}: notification send failed (no SID returned)")

    return RedirectResponse(url="/staff/reservations", status_code=303)


# ---------------------------------------------------------------------------
# Settings (manager/owner only)
# ---------------------------------------------------------------------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    require_manager(session)
    settings = db.query(ReservationSettings).first()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "session": session, "saved": False},
    )


@router.post("/settings")
async def update_settings(
    request: Request,
    reservations_enabled: bool = Form(default=False),
    open_from: str = Form(),
    open_to: str = Form(),
    slot_interval: int = Form(),
    max_per_slot: int = Form(),
    max_party_size: int = Form(),
    large_party_threshold: int = Form(default=8),
    large_party_phone: str = Form(default=""),
    confirm_message: str = Form(default=""),
    deny_message: str = Form(default=""),
    cancel_message: str = Form(default=""),
    chatbot_paused: bool = Form(default=False),
    paused_away_message: str = Form(default=""),
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    require_manager(session)
    settings = db.query(ReservationSettings).first()
    if settings is None:
        settings = ReservationSettings()
        db.add(settings)

    settings.reservations_enabled = reservations_enabled
    settings.open_from = open_from
    settings.open_to = open_to
    settings.slot_interval = slot_interval
    settings.max_per_slot = max_per_slot
    settings.max_party_size = max_party_size
    settings.large_party_threshold = large_party_threshold
    settings.large_party_phone = large_party_phone
    settings.confirm_message = confirm_message
    settings.deny_message = deny_message
    settings.cancel_message = cancel_message
    settings.chatbot_paused = chatbot_paused
    settings.paused_away_message = paused_away_message
    settings.updated_by = session.get("id")
    settings.updated_at = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "session": session, "saved": True},
    )


# ---------------------------------------------------------------------------
# Client profile (read-only)
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_profile(
    client_id: int,
    request: Request,
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return templates.TemplateResponse(
        "client.html",
        {"request": request, "client": client, "session": session},
    )
