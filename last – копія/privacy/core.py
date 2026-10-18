"""Спільні частини privacy-механізмів: транзакції, принципал, права, аудит."""
from __future__ import annotations

import datetime as _dt
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from flask import session
from psycopg2.extras import Json

import db
from .logging_setup import get_correlation_id

security_log = logging.getLogger("privacy.security")


# ---------------------------------------------------------------------------
# Транзакція: усе або нічого
# ---------------------------------------------------------------------------
@contextmanager
def transaction():
    """Курсор в одній транзакції: commit при успіху, rollback при будь-якій помилці."""
    with db.get_conn() as conn:
        conn.rollback()  # з'єднання з пулу могло лишитись у незавершеній транзакції
        try:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO app, public")
                yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Хто виконує дію (authenticated principal) і що йому дозволено
# ---------------------------------------------------------------------------
# Явно визначені повноваження. Доступ до чужих даних — лише через них.
ROLE_PERMISSIONS = {
    "Admin": frozenset({"privacy.export.any", "privacy.erase.any", "marketing.send"}),
    "Operator": frozenset({"marketing.send"}),
}


@dataclass(frozen=True)
class Principal:
    id: int
    role: str

    @property
    def ref(self) -> str:
        return subject_ref(self.id)

    def has(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


def load_principal(cur) -> Optional[Principal]:
    """Принципал береться з сесії, але id і роль — з БД (сесія могла застаріти)."""
    login = (session.get("user") or {}).get("login")
    if not login:
        return None
    cur.execute(
        "SELECT id, role FROM keys WHERE login = %s AND account_status = 'active'", (login,)
    )
    row = cur.fetchone()
    return Principal(id=row[0], role=row[1]) if row else None


def may_act_on(principal: Principal, subject_id: int, permission: Optional[str] = None) -> bool:
    """Сам суб'єкт — завжди; інший користувач — лише з явним повноваженням."""
    if principal.id == subject_id:
        return True
    return permission is not None and principal.has(permission)


# ---------------------------------------------------------------------------
# Аудит без PII
# ---------------------------------------------------------------------------
def subject_ref(user_id) -> str:
    """Безпечне посилання на суб'єкта: технічний id, а не login/email."""
    return f"user:{user_id}" if user_id is not None else "anonymous"


def security_event(event: str, actor: str, subject: str, result: str, **fields) -> None:
    """Подія безпеки в журналі: факт, actor/subject, результат, correlation ID."""
    security_log.info(
        "%s actor=%s subject=%s result=%s", event, actor, subject, result,
        extra={"event": event, "actor": actor, "subject": subject, "result": result, **fields},
    )


def write_audit(cur, event_type: str, actor: str, subject: str, result: str, details=None) -> None:
    cur.execute(
        """INSERT INTO privacy_audit (event_type, actor_ref, subject_ref, result, correlation_id, details)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (event_type, actor, subject, result, get_correlation_id(), Json(details or {})),
    )


def iso_utc(value):
    """Однозначний формат часу в API: ISO 8601, UTC, суфікс Z."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_dt.timezone.utc)
        return value.astimezone(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(value, _dt.date):
        return value.isoformat()
    return value


def now_utc_iso() -> str:
    return iso_utc(_dt.datetime.now(_dt.timezone.utc))
