"""Privacy Engineering (ЛР4): безпечне логування, експорт, анонімізація, згоди.

Підключення в app.py:
    from privacy import configure_logging, init_app
    configure_logging()          # замість logging.basicConfig(...)
    ...
    init_app(app)                # у create_app() після реєстрації blueprints
"""
from __future__ import annotations

import re

from flask import g, request, session

import db
from .logging_setup import (configure_logging, get_correlation_id, reset_correlation_id,
                            set_correlation_id)
from .web import bp

__all__ = ["configure_logging", "init_app"]

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _begin_request():
    incoming = request.headers.get("X-Request-ID", "")
    g._privacy_cid_token = set_correlation_id(incoming if _REQUEST_ID_RE.match(incoming) else None)
    _drop_stale_session()


def _end_request(response):
    response.headers["X-Request-ID"] = get_correlation_id()
    return response


def _teardown(exc=None):
    token = g.pop("_privacy_cid_token", None)
    if token is not None:
        try:
            reset_correlation_id(token)
        except ValueError:
            pass


def _drop_stale_session():
    """Сесія Flask зберігається в cookie, тож її неможливо «видалити» на сервері.
    Тому на кожному запиті перевіряємо, що акаунт із сесії ще активний: після
    анонімізації старого login більше немає -> сесія очищується, і роль із cookie
    (наприклад Admin) вже не дає доступу."""
    login = (session.get("user") or {}).get("login")
    if not login:
        return
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO app, public;")
                cur.execute("SELECT COUNT(*) FROM keys WHERE login = %s AND account_status = 'active'",
                            (login,))
                row = cur.fetchone()
            rollback = getattr(conn, "rollback", None)
            if rollback:
                rollback()
    except Exception:
        return  # БД недоступна: рішення приймуть самі маршрути (вони теж ідуть у БД)
    if row is not None and row[0] == 0:
        session.clear()


def init_app(app):
    app.before_request(_begin_request)
    app.after_request(_end_request)
    app.teardown_request(_teardown)
    app.register_blueprint(bp)
    return app
