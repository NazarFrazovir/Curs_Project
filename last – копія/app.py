import os
from flask import Flask, render_template, session, redirect, url_for
from dotenv import load_dotenv

from db import get_conn, release_conn
from auth import bp as auth_bp
from inventory import bp as inv_bp
from reports import bp as reports_bp

load_dotenv()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_secret")

    # ===== Blueprints =====
    app.register_blueprint(auth_bp)
    app.register_blueprint(inv_bp)
    app.register_blueprint(reports_bp)

    # ===== Локальні хелпери для коротких запитів на головній =====
    def _one(sql, params=()):
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("SET search_path TO app, public;")
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def _all(sql, params=()):
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("SET search_path TO app, public;")
                cur.execute(sql, params)
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception:
            return []

    # ===== Головна =====
    @app.route("/")
    def dashboard():
        user = session.get("user")
        if not user:
            return redirect(url_for("auth.login_get"))

        stats = {
            "suppliers": _one("SELECT COUNT(*) FROM suppliers WHERE is_active=true") or 0,
            "customers": _one("SELECT COUNT(*) FROM customers WHERE archived_at IS NULL") or 0,
            "products":  _one("SELECT COUNT(*) FROM products  WHERE is_active=true") or 0,
            "moves":     _one("SELECT COUNT(*) FROM stock_movements WHERE is_canceled=false") or 0,
        }

        # Оціночна вартість складу (якщо існує view stock_balance)
        stock_value = _one("""
            SELECT COALESCE(SUM(b.balance_qty * p.sale_price), 0)
            FROM stock_balance b
            JOIN products p ON p.id = b.product_id
        """)
        if stock_value is not None:
            stats["stock_value"] = float(stock_value)

        recent_moves = _all("""
            SELECT m.id,
                   to_char(m.movement_dt, 'YYYY-MM-DD HH24:MI') AS dt,
                   m.mtype, m.qty, m.price, (m.qty*m.price) AS sum_total,
                   p.name AS product_name, m.is_canceled
            FROM stock_movements m
            JOIN products p ON p.id = m.product_id
            ORDER BY m.id DESC
            LIMIT 7
        """)

        low_stock = _all("""
            SELECT product_id, product, unit, supplier, balance_qty
            FROM stock_balance
            WHERE balance_qty <= 5
            ORDER BY balance_qty ASC
            LIMIT 7
        """)

        recent_archives = _all("""
            SELECT to_char(performed_at, 'YYYY-MM-DD HH24:MI') AS performed_at,
                   entity_type, entity_id, action, performed_by
            FROM archive_history
            ORDER BY performed_at DESC
            LIMIT 7
        """)

        return render_template(
            "dashboard.html",
            user=user,
            stats=stats,
            recent_moves=recent_moves,
            low_stock=low_stock,
            recent_archives=recent_archives
        )

    # ===== Глобальні значення в шаблонах =====
    @app.context_processor
    def inject_globals():
        """
        pending_requests — кількість заявок (для Admin),
        prefs — персональні налаштування користувача (тема/щільність/per_page/тощо).
        """
        user = session.get("user") or {}
        prefs = session.get("prefs") or {}   # кладеться у сесію при логіні/оновленні налаштувань

        pending = 0
        if user.get("role") == "Admin":
            try:
                with get_conn() as conn, conn.cursor() as cur:
                    cur.execute("SET search_path TO app, public;")
                    cur.execute("SELECT COUNT(*) FROM access_requests WHERE status='pending'")
                    row = cur.fetchone()
                    pending = (row[0] if row else 0) or 0
            except Exception:
                pending = 0

        return dict(pending_requests=pending, prefs=prefs)

    # Закриваємо конекшени після запитів
    app.teardown_appcontext(release_conn)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
