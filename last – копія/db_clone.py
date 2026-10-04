import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import time

DATABASE_URL = os.environ.get("DATABASE_URL")

POOL = None
if DATABASE_URL:
    for attempt in range(10):
        try:
            POOL = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
            break
        except psycopg2.OperationalError:
            time.sleep(2)

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
    pass