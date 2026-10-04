import os
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool

DATABASE_URL = os.environ.get("DATABASE_URL")
CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "2"))

POOL = None
if DATABASE_URL:
    for attempt in range(10):
        try:
            POOL = psycopg2.pool.SimpleConnectionPool(
                1, 10, dsn=DATABASE_URL, connect_timeout=CONNECT_TIMEOUT)
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