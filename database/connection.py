import os
import psycopg
from psycopg import connection as PGConnection
from pathlib import Path

#path() turn whats in the parentheses into a path object
#os.getenv checks if there is a env variable MAITRED_DB that can be set outside of the code
# if not checks for maitred.db if not exists creates a db

DB_URL = os.getenv("MAITRED_DB", "dbname=maitred user=postgres password=postgres host=localhost port=5433")

#This is a type hint, indicating that this function is expected to return an object of type sqlite3.Connection.
def connect() -> PGConnection:
    """Return a connection to the PostgreSQL database using environment variable or default config (port 5433)."""
    return psycopg.connect(DB_URL)