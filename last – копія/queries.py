"""Короткі запити до БД для головної сторінки.

Будь-яка помилка БД перетворюється на безпечне значення за замовчуванням,
щоб головна сторінка відкривалась навіть при недоступній базі.
"""
from db import get_conn


def _run(sql, params, reader, default):
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SET search_path TO app, public;")
            cur.execute(sql, params)
            return reader(cur)
    except Exception:
        return default


def _first_value(cur):
    row = cur.fetchone()
    return row[0] if row else None


def _all_dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def scalar(sql, params=()):
    """Перше значення першого рядка або None."""
    return _run(sql, params, _first_value, None)


def rows(sql, params=()):
    """Список рядків як словників або [] при помилці."""
    return _run(sql, params, _all_dicts, [])
