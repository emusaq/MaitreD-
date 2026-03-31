import psycopg
from psycopg import Connection as PGConnection
from sqlalchemy.engine import make_url

from config import get_database_url

#path() turn whats in the parentheses into a path object
#os.getenv checks if there is a env variable MAITRED_DB that can be set outside of the code
# if not checks for maitred.db if not exists creates a db

# return psycopg.connect(DB_URL) postgres pycogpg conn
#engine = create_engine('postgresql+psycopg2://user:password@hostname/database_name') template for engine creation

def connect() -> PGConnection:
    """Return a raw psycopg connection for schema/maintenance tasks.

    Uses the same database target as the ORM/Alembic config.
    Remember to conn.close() when done.
    """
    url = make_url(get_database_url())
    if not url.drivername.startswith("postgresql"):
        raise ValueError(
            "manage.py raw connection only supports PostgreSQL DATABASE_URL values."
        )
    psycopg_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    return psycopg.connect(psycopg_url)
