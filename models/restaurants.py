from typing import List, Optional
from sqlalchemy.orm import Session

from models.models import SessionLocal, Restaurant


def list_restaurants(db: Session = SessionLocal()) -> List[Restaurant]:
    """Return a list of all restaurants."""
    return db.query(Restaurant).order_by(Restaurant.name).all()


def get_restaurant_by_id(
    restaurant_id: int, db: Session = SessionLocal()
) -> Optional[Restaurant]:
    """Return a restaurant by ID."""
    return db.get(Restaurant, restaurant_id)


def create_restaurant(
    name: str,
    location: Optional[str] = None,
    db: Session = SessionLocal()
) -> int:
    """Create a new restaurant and return its ID."""
    new_restaurant = Restaurant(name=name, location=location)
    db.add(new_restaurant)
    db.commit()
    db.refresh(new_restaurant)
    return new_restaurant.restaurant_id


def update_restaurant(
    restaurant_id: int,
    name: str,
    location: Optional[str],
    db: Session = SessionLocal()
) -> bool:
    """Update the name and/or location of a restaurant."""
    restaurant = get_restaurant_by_id(restaurant_id, db)
    if restaurant:
        restaurant.name = name
        restaurant.location = location
        db.commit()
        return True
    return False


def delete_restaurant(
    restaurant_id: int, db: Session = SessionLocal()
) -> bool:
    """Delete a restaurant by ID."""
    restaurant = get_restaurant_by_id(restaurant_id, db)
    if restaurant:
        db.delete(restaurant)
        db.commit()
        return True
    return False
