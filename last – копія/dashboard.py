"""Головна сторінка та глобальні значення шаблонів."""
from flask import redirect, render_template, session, url_for

from queries import rows, scalar

COUNT_QUERIES = {
    "suppliers": "SELECT COUNT(*) FROM suppliers WHERE is_active=true",
    "customers": "SELECT COUNT(*) FROM customers WHERE archived_at IS NULL",
    "products":  "SELECT COUNT(*) FROM products  WHERE is_active=true",
    "moves":     "SELECT COUNT(*) FROM stock_movements WHERE is_canceled=false",
}

# Оціночна вартість складу (якщо існує view stock_balance)
STOCK_VALUE_SQL = """
    SELECT COALESCE(SUM(b.balance_qty * p.sale_price), 0)
    FROM stock_balance b
    JOIN products p ON p.id = b.product_id
"""

RECENT_MOVES_SQL = """
    SELECT m.id,
           to_char(m.movement_dt, 'YYYY-MM-DD HH24:MI') AS dt,
           m.mtype, m.qty, m.price, (m.qty*m.price) AS sum_total,
           p.name AS product_name, m.is_canceled
    FROM stock_movements m
    JOIN products p ON p.id = m.product_id
    ORDER BY m.id DESC
    LIMIT 7
"""

LOW_STOCK_SQL = """
    SELECT product_id, product, unit, supplier, balance_qty
    FROM stock_balance
    WHERE balance_qty <= 5
    ORDER BY balance_qty ASC
    LIMIT 7
"""

RECENT_ARCHIVES_SQL = """
    SELECT to_char(performed_at, 'YYYY-MM-DD HH24:MI') AS performed_at,
           entity_type, entity_id, action, performed_by
    FROM archive_history
    ORDER BY performed_at DESC
    LIMIT 7
"""

PENDING_REQUESTS_SQL = "SELECT COUNT(*) FROM access_requests WHERE status='pending'"


def collect_stats():
    stats = {name: scalar(sql) or 0 for name, sql in COUNT_QUERIES.items()}
    stock_value = scalar(STOCK_VALUE_SQL)
    if stock_value is not None:
        stats["stock_value"] = float(stock_value)
    return stats


def dashboard():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_get"))
    return render_template(
        "dashboard.html",
        user=user,
        stats=collect_stats(),
        recent_moves=rows(RECENT_MOVES_SQL),
        low_stock=rows(LOW_STOCK_SQL),
        recent_archives=rows(RECENT_ARCHIVES_SQL),
    )


def pending_requests(user):
    """Кількість заявок на доступ — лише для Admin."""
    if user.get("role") != "Admin":
        return 0
    return scalar(PENDING_REQUESTS_SQL) or 0


def inject_globals():
    """pending_requests та prefs доступні в усіх шаблонах."""
    user = session.get("user") or {}
    prefs = session.get("prefs") or {}
    return dict(pending_requests=pending_requests(user), prefs=prefs)
