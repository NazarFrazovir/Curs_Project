"""Сповіщення про низькі залишки і перевірка живості сервісу (JSON API)."""
import os

from flask import Blueprint, jsonify, request

import db
from resilience import TRANSIENT_ERRORS

bp = Blueprint("alerts", __name__, url_prefix="/api")

DEFAULT_THRESHOLD = float(os.environ.get("STOCK_ALERT_THRESHOLD", "10"))

LOW_STOCK_SQL = """
    SELECT product_id, product, unit, supplier, balance_qty
    FROM stock_balance
    WHERE balance_qty < %s
    ORDER BY balance_qty, product
"""


def _threshold():
    raw = request.args.get("below")
    if raw is None:
        return DEFAULT_THRESHOLD
    value = float(raw)
    if value < 0:
        raise ValueError("below must be >= 0")
    return value


@bp.get("/stock-alerts")
def stock_alerts():
    try:
        threshold = _threshold()
    except ValueError:
        return jsonify(status="error", message="Параметр below має бути невід'ємним числом"), 400
    rows = db.fetchall(LOW_STOCK_SQL, (threshold,))
    items = [{"product_id": r[0], "product": r[1], "unit": r[2], "supplier": r[3],
              "balance_qty": float(r[4])} for r in rows]
    return jsonify(status="ok", threshold=threshold, count=len(items), items=items)


@bp.get("/health")
def health():
    try:
        db.fetchone("SELECT 1")
    except (RuntimeError, *TRANSIENT_ERRORS):
        return jsonify(status="down", db="unavailable"), 503
    return jsonify(status="ok", db="up")
