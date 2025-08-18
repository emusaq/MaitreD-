from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json

from database.connection import connect

UPCOMING_WINDOW_HOURS = 48


def upsert_reservation(
    client_id: int,
    date: str,
    time: str,
    covers: int,
    occasion: Optional[str] = None,
    seating: Optional[str] = None,
    dietary: Optional[str] = None,
    special_requests: Optional[str] = None,
    source: Optional[str] = None,
    language_guess: Optional[str] = None,
    parsed_party_size: Optional[int] = None,
    parsed_date: Optional[str] = None,
    parsed_time: Optional[str] = None,
    created_by_bot: bool = False,
) -> int:
    """Insert or update a reservation record.

    The combination of ``client_id`` and ``reservation_time`` is treated as
    unique.  If a record already exists for that tuple, the entry is updated
    rather than duplicated.
    """
    reservation_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")

    notes_json: Dict[str, Any] = {
        "occasion": occasion,
        "seating": seating,
        "dietary": dietary,
        "special_requests": special_requests,
        "source": source,
        "language_guess": language_guess,
        "parsed_party_size": parsed_party_size,
        "parsed_date": parsed_date,
        "parsed_time": parsed_time,
        "created_by_bot": created_by_bot,
    }

    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Reservations (client_id, reservation_time, covers, notes_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (client_id, reservation_time)
            DO UPDATE SET covers = EXCLUDED.covers,
                          notes_json = EXCLUDED.notes_json,
                          updated_at = CURRENT_TIMESTAMP
            RETURNING reservation_id
            """,
            (client_id, reservation_time, covers, json.dumps(notes_json)),
        )
        reservation_id = cur.fetchone()[0]
        conn.commit()
        return reservation_id


def get_upcoming_reservation(client_id: int) -> Optional[Dict[str, Any]]:
    """Return the soonest reservation within the upcoming window.

    Args:
        client_id: The client to query for.

    Returns:
        A dictionary with reservation details or ``None`` if no upcoming
        reservation exists for the client.
    """
    now = datetime.utcnow()
    window_end = now + timedelta(hours=UPCOMING_WINDOW_HOURS)

    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT reservation_id, client_id, reservation_time, covers, notes_json
            FROM Reservations
            WHERE client_id = %s
              AND reservation_time BETWEEN %s AND %s
            ORDER BY reservation_time ASC
            LIMIT 1
            """,
            (client_id, now, window_end),
        )
        row = cur.fetchone()
        if not row:
            return None

        reservation_id, client_id, reservation_time, covers, notes_json = row
        return {
            "reservation_id": reservation_id,
            "client_id": client_id,
            "reservation_time": reservation_time,
            "covers": covers,
            "notes_json": notes_json,
        }
