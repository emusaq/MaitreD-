"""initial_schema

Revision ID: 02b1ec5ab21e
Revises:
Create Date: 2026-03-30 12:38:18.342180

"""
from typing import Sequence, Union

from alembic import op

from models.models import Base


revision: str = "02b1ec5ab21e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
