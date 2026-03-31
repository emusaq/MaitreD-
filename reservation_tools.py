"""
OpenAI function-calling definitions and execution logic for reservations.

This bridges the LLM conversation (webapp.py) with the actual database.
Business logic lives in services/reservation.py; this file contains only
the OpenAI tool schemas and a thin dispatcher.
"""
import json
from typing import Optional
from sqlalchemy.orm import Session

from services.reservation import ReservationService
from utils import logger

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
            result = ReservationService.list_open_times(args["date_iso"], args["party_size"], db)
        elif tool_name == "check_availability":
            result = ReservationService.check_availability(
                args["date_iso"], args["time_24h"], args["party_size"], db
            )
        elif tool_name == "create_reservation":
            result = ReservationService.create_reservation(
                args["slot_id"],
                args["party_size"],
                db,
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
