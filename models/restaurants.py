from typing import List, Optional
from sqlalchemy.orm import Session

from models.models import SessionLocal, Restaurant


def list_restaurants(db: Optional[Session] = None) -> List[Restaurant]:
    """Return a list of all restaurants."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return db.query(Restaurant).order_by(Restaurant.name).all()
    finally:
        if _close:
            db.close()


def get_restaurant_by_id(
    restaurant_id: int, db: Optional[Session] = None
) -> Optional[Restaurant]:
    """Return a restaurant by ID."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        return db.get(Restaurant, restaurant_id)
    finally:
        if _close:
            db.close()


def create_restaurant(
    name: str,
    location: Optional[str] = None,
    db: Optional[Session] = None,
) -> int:
    """Create a new restaurant and return its ID."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        new_restaurant = Restaurant(name=name, location=location)
        db.add(new_restaurant)
        db.commit()
        db.refresh(new_restaurant)
        return new_restaurant.restaurant_id
    finally:
        if _close:
            db.close()


def update_restaurant(
    restaurant_id: int,
    name: str,
    location: Optional[str],
    db: Optional[Session] = None,
) -> bool:
    """Update the name and/or location of a restaurant."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        restaurant = get_restaurant_by_id(restaurant_id, db)
        if restaurant:
            restaurant.name = name
            restaurant.location = location
            db.commit()
            return True
        return False
    finally:
        if _close:
            db.close()


def delete_restaurant(
    restaurant_id: int, db: Optional[Session] = None
) -> bool:
    """Delete a restaurant by ID."""
    _close = db is None
    if db is None:
        db = SessionLocal()
    try:
        restaurant = get_restaurant_by_id(restaurant_id, db)
        if restaurant:
            db.delete(restaurant)
            db.commit()
            return True
        return False
    finally:
        if _close:
            db.close()
