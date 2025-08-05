from typing import List, Tuple, Optional
from database.connection import connect


def list_restaurants() -> List[Tuple]:
    """Return a list of all restaurants."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT restaurant_id, name, location FROM Restaurants ORDER BY name")
        return cur.fetchall()


def get_restaurant_by_id(restaurant_id: int) -> Optional[Tuple]:
    """Return a restaurant by ID."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Restaurants WHERE restaurant_id = %s", (restaurant_id,))
        return cur.fetchone()


def create_restaurant(name: str, location: Optional[str] = None) -> int:
    """Create a new restaurant and return its ID."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Restaurants (name, location) VALUES (%s, %s) RETURNING restaurant_id",
            (name, location)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id


def update_restaurant(restaurant_id: int, name: str, location: Optional[str]) -> bool:
    """Update the name and/or location of a restaurant."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE Restaurants SET name = %s, location = %s WHERE restaurant_id = %s",
            (name, location, restaurant_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_restaurant(restaurant_id: int) -> bool:
    """Delete a restaurant by ID."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM Restaurants WHERE restaurant_id = %s", (restaurant_id,))
        conn.commit()
        return cur.rowcount > 0

