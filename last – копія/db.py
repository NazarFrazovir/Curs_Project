import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")

POOL = None
if DATABASE_URL:
    POOL = psycopg2.pool.SimpleConnectionPool(
        1, 10, dsn=DATABASE_URL
    )

@contextmanager
def get_conn():
    if not POOL:
        raise RuntimeError("Database pool is not initialized. Set DATABASE_URL in .env")
    conn = POOL.getconn()
    try:
        yield conn
    finally:
        POOL.putconn(conn)

def release_conn(exception=None):
    # nothing special here; pool will manage connections
    pass
