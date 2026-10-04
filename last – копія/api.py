"""JSON API: залишки на складі з Retry та Fallback (graceful degradation)."""
import logging
import time

from flask import Blueprint, jsonify

from db import get_conn
from resilience import TRANSIENT_ERRORS, call_with_retry

bp = Blueprint("api", __name__, url_prefix="/api")
log = logging.getLogger(__name__)

# Останні успішно отримані дані (stale cache для fallback).
_cache = {"items": None, "ts": None}

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


def _fallback(exc):
    log.warning("FALLBACK /api/balance: database unavailable after retries (%s)", exc)
    if _cache["items"] is not None:
        age = int(time.time() - _cache["ts"])
        resp = jsonify(status="degraded", degraded=True, source="cache",
                       cache_age_s=age, items=_cache["items"])
        resp.headers["Warning"] = '110 - "Response is stale"'
        return resp, 200
    resp = jsonify(status="unavailable", degraded=True, items=[],
                   message="Дані про залишки тимчасово недоступні, спробуйте пізніше")
    resp.headers["Retry-After"] = "5"
    return resp, 503


@bp.get("/balance")
def balance():
    try:
        items = call_with_retry(_query_balance)
    except TRANSIENT_ERRORS as exc:
        return _fallback(exc)
    _cache.update(items=items, ts=time.time())
    return jsonify(status="ok", degraded=False, source="db", items=items)
