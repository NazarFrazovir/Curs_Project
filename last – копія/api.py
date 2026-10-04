"""JSON API: залишки на складі (версія без механізмів стійкості)."""
from flask import Blueprint, jsonify

from db import get_conn

bp = Blueprint("api", __name__, url_prefix="/api")

BALANCE_SQL = """
    SELECT product_id, product, unit, supplier, balance_qty
    FROM stock_balance
    ORDER BY product
"""


def _query_balance():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(BALANCE_SQL)
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for row in rows:
        row["balance_qty"] = float(row["balance_qty"])
    return rows


@bp.get("/balance")
def balance():
    return jsonify(status="ok", degraded=False, source="db", items=_query_balance())