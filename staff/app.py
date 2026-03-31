"""Front-of-house staff webapp router."""
from datetime import date, datetime, time as dt_time
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from models.models import get_db, ReservationSettings, Client
from models.reservation import (
    get_reservations_for_date,
    get_reservations_for_date_simple,
    get_reservation_by_id,
    update_reservation_status,
)
from utils import send_message, send_template_message, logger
from staff.auth import (
    get_current_employee,
    require_manager,
    create_session_cookie,
    authenticate,
    COOKIE_NAME,
)

import os
from config import (
    SECURE_COOKIES as _secure_cookies,
    TWILIO_CONFIRM_TEMPLATE_SID as _confirm_template_sid,
    TWILIO_DENY_TEMPLATE_SID as _deny_template_sid,
    TWILIO_CANCEL_TEMPLATE_SID as _cancel_template_sid,
)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)

router = APIRouter(prefix="/staff")


def _format_time(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value)


def _format_date(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _should_set_secure_cookie(request: Request) -> bool:
    if not _secure_cookies:
        return False
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or forwarded_proto == "https"


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
        secure=_should_set_secure_cookie(request),
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
    rows = get_reservations_for_date_simple(today, db)

    reservations = [
        {
            "id": row[0],
            "slot_id": row[1],
            "time_24h": _format_time(row[2]),
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
    rows = get_reservations_for_date(target_date, db)

    reservations = [
        {
            "id": row[0],
            "slot_id": row[1],
            "date_iso": _format_date(row[2]),
            "time_24h": _format_time(row[3]),
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
    reservation = get_reservation_by_id(reservation_id, db)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    update_reservation_status(reservation_id, "confirmed", db)

    settings_row = db.query(ReservationSettings).first()
    confirm_msg = settings_row.confirm_message if settings_row else "Your reservation at Garufa has been confirmed. We look forward to welcoming you."
    guest_phone = reservation.guest_phone
    if guest_phone:
        if _confirm_template_sid:
            sid = send_template_message(guest_phone, _confirm_template_sid)
        else:
            # No template configured — fall back to free-form (requires active 24h session)
            logger.warning(f"confirm_reservation id={reservation_id}: TWILIO_CONFIRM_TEMPLATE_SID not set, falling back to send_message")
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
    reservation = get_reservation_by_id(reservation_id, db)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    update_reservation_status(reservation_id, "denied", db)

    guest_phone = reservation.guest_phone
    if guest_phone:
        settings_row = db.query(ReservationSettings).first()
        msg = custom_message.strip() or (settings_row.deny_message if settings_row else "")
        if _deny_template_sid:
            # Pass custom_message as template variable "1" if provided
            variables = {"1": msg} if msg else None
            sid = send_template_message(guest_phone, _deny_template_sid, variables)
        else:
            logger.warning(f"deny_reservation id={reservation_id}: TWILIO_DENY_TEMPLATE_SID not set, falling back to send_message")
            sid = send_message(guest_phone, msg) if msg else None
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
    reservation = get_reservation_by_id(reservation_id, db)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    update_reservation_status(reservation_id, "cancelled", db)

    guest_phone = reservation.guest_phone
    if guest_phone:
        settings_row = db.query(ReservationSettings).first()
        msg = custom_message.strip() or (settings_row.cancel_message if settings_row else "")
        if _cancel_template_sid:
            variables = {"1": msg} if msg else None
            sid = send_template_message(guest_phone, _cancel_template_sid, variables)
        else:
            logger.warning(f"cancel_reservation id={reservation_id}: TWILIO_CANCEL_TEMPLATE_SID not set, falling back to send_message")
            sid = send_message(guest_phone, msg) if msg else None
        if sid is None:
            logger.warning(f"cancel_reservation id={reservation_id}: notification send failed (no SID returned)")

    return RedirectResponse(url="/staff/reservations", status_code=303)


# ---------------------------------------------------------------------------
# Settings (manager/owner only)
# ---------------------------------------------------------------------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    saved: bool = Query(default=False),
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    require_manager(session)
    settings = db.query(ReservationSettings).first()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "session": session, "saved": saved},
    )


@router.post("/settings")
async def update_settings(
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

    # Parse time strings ("HH:MM" or "HH:MM:SS") into datetime.time objects
    h, m = open_from.split(":")[:2]
    settings.open_from = dt_time(int(h), int(m))
    h, m = open_to.split(":")[:2]
    settings.open_to = dt_time(int(h), int(m))

    settings.reservations_enabled = reservations_enabled
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

    return RedirectResponse(url="/staff/settings?saved=1", status_code=303)


# ---------------------------------------------------------------------------
# Quick toggle reservations (dashboard shortcut)
# ---------------------------------------------------------------------------

@router.post("/toggle-reservations")
async def toggle_reservations(
    session: dict = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    require_manager(session)
    settings = db.query(ReservationSettings).first()
    if settings is None:
        settings = ReservationSettings()
        db.add(settings)
    settings.reservations_enabled = not settings.reservations_enabled
    settings.updated_by = session.get("id")
    settings.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url="/staff/", status_code=303)


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
