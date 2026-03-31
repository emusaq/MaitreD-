from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config object
alembic_config = context.config

# Set up Python logging from alembic.ini
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Import ORM metadata — required for --autogenerate
from models.models import Base  # noqa: E402
from config import get_database_url  # noqa: E402
target_metadata = Base.metadata


def _get_url() -> str:
    return get_database_url()


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    cfg = alembic_config.get_section(alembic_config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
