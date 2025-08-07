import os
import psycopg
import psycopg2
from psycopg import connection as PGConnection
from pathlib import Path
from sqlalchemy import create_engine, engine
from sqlalchemy.orm import sessionmaker, Session

#path() turn whats in the parentheses into a path object
#os.getenv checks if there is a env variable MAITRED_DB that can be set outside of the code
# if not checks for maitred.db if not exists creates a db

# return psycopg.connect(DB_URL) postgres pycogpg conn
#engine = create_engine('postgresql+psycopg2://user:password@hostname/database_name') template for engine creation

DB_URL_POST = os.getenv("MAITRED_DB", "dbname=maitred user=postgres password=postgres host=localhost port=5433")
DB_URL_ALC = 'postgresql+psycopg2://postgres:postgres@localhost:5433/maitred'

def connect() -> Session:
    """Return a connection to the database using environment variable or default config (port 5433). Use session.close() when done"""
    

    engine = create_engine(DB_URL_ALC)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return psycopg.connect(DB_URL_POST)
