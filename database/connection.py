import os
import psycopg
from psycopg import Connection as PGConnection

#path() turn whats in the parentheses into a path object
#os.getenv checks if there is a env variable MAITRED_DB that can be set outside of the code
# if not checks for maitred.db if not exists creates a db

# return psycopg.connect(DB_URL) postgres pycogpg conn
#engine = create_engine('postgresql+psycopg2://user:password@hostname/database_name') template for engine creation

DB_URL_POST = os.getenv(
    "MAITRED_DB",
    "dbname=maitred user=postgres password=postgres host=localhost port=5433",
)

def connect() -> PGConnection:
    """Return a raw psycopg connection for schema/maintenance tasks.

    Uses env var MAITRED_DB if provided; otherwise defaults to localhost:5433.
    Remember to conn.close() when done.
    """
    return psycopg.connect(DB_URL_POST)
