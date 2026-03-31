from typing import Dict, List

from sqlalchemy import Engine, inspect


STAFF_PORTAL_REQUIRED_COLUMNS: Dict[str, set[str]] = {
    "reservations": {
        "id",
        "date_iso",
        "time_24h",
        "party_size",
        "slot_id",
        "client_id",
        "status",
        "guest_name",
        "occasion",
        "guest_phone",
        "note",
        "note_author",
    },
    "reservation_settings": {
        "id",
        "restaurant_id",
        "reservations_enabled",
        "open_from",
        "open_to",
        "slot_interval",
        "max_per_slot",
        "max_party_size",
        "large_party_threshold",
        "large_party_phone",
        "confirm_message",
        "deny_message",
        "cancel_message",
        "chatbot_paused",
        "paused_away_message",
        "updated_at",
        "updated_by",
    },
}


def find_staff_portal_schema_inconsistencies(engine: Engine) -> List[str]:
    inspector = inspect(engine)
    issues: List[str] = []

    for table_name, required_columns in STAFF_PORTAL_REQUIRED_COLUMNS.items():
        if not inspector.has_table(table_name):
            issues.append(f"missing table: {table_name}")
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = sorted(required_columns - existing_columns)
        if missing_columns:
            issues.append(
                f"{table_name} missing columns: {', '.join(missing_columns)}"
            )

    return issues
