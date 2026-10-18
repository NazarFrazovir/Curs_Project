"""Right of Access, GDPR Art. 15 — Personal Data Export (Завдання 2).

Контракт стабільний: кожна секція присутня завжди (порожній список / null, якщо
даних немає), час — ISO 8601 UTC, поля названі однозначно, версія схеми в meta.
"""
from __future__ import annotations

import json
from typing import Optional

from .core import iso_utc, now_utc_iso

SCHEMA_VERSION = "1.0"

# Пояснення джерела кожної секції (для документації й демонстрації)
SOURCES = {
    "profile": "app.keys — обліковий запис: логін, роль, ПІБ, email, телефон",
    "settings": "app.user_prefs — налаштування інтерфейсу",
    "access_requests": "app.access_requests — заявки на зміну ролі",
    "activity.archive_history": "app.archive_history — дії користувача (performed_by)",
    "consents.current": "app.user_consents — поточний стан згод за метами",
    "consents.history": "app.consent_events — незмінна історія GRANT/REVOKE",
    "communications.marketing_emails": "app.marketing_outbox — маркетингові листи",
    "analytics.events": "app.analytics_events — необов'язкова аналітика",
}

# Documented omissions: що свідомо НЕ повертається і чому
EXCLUDED = [
    {"fields": ["keys.password"],
     "reason": "секрет автентифікації (security-sensitive), не повертається ніколи"},
    {"fields": ["keys.account_status", "app.privacy_audit"],
     "reason": "внутрішні службові записи безпеки"},
    {"fields": ["access_requests.processed_by"],
     "reason": "ідентифікатор іншого користувача (адміністратора, що розглянув заявку)"},
    {"fields": ["consent_events.correlation_id"],
     "reason": "технічний ідентифікатор запиту, не персональні дані суб'єкта"},
    {"fields": ["suppliers/customers/products/agreements.archived_by", "stock_movements.canceled_by"],
     "reason": "дублюють записи activity.archive_history, тому не повторюються"},
    {"fields": ["app.customers", "app.suppliers", "app.stock_movements", "app.agreements"],
     "reason": "дані контрагентів складу (інших осіб), а не облікового запису суб'єкта"},
]


def _rows(cur, sql, params):
    cur.execute(sql, params)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _times(row: dict, *fields) -> dict:
    for f in fields:
        row[f] = iso_utc(row.get(f))
    return row


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value if value is not None else {}


def build_export(cur, subject_id: int) -> Optional[dict]:
    """Зібрати всі персональні дані суб'єкта. None — якщо активного суб'єкта немає."""
    cur.execute(
        """SELECT id, login, role, full_name, email, phone, created_at, last_login
             FROM keys WHERE id = %s AND account_status = 'active'""",
        (subject_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    _, login, role, full_name, email, phone, created_at, last_login = row

    profile = {
        "subject_id": subject_id,
        "login": login,
        "role": role,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "account_created_at": iso_utc(created_at),
        "last_login_at": iso_utc(last_login),
    }

    prefs = _rows(cur, """SELECT theme, density, per_page, default_filter, updated_at
                            FROM user_prefs WHERE user_login = %s""", (login,))
    settings = None
    if prefs:
        settings = _times(prefs[0], "updated_at")
        settings["default_filter"] = _json_value(settings["default_filter"])

    access_requests = [
        _times(r, "requested_at", "processed_at")
        for r in _rows(cur, """SELECT id, requested_role, message, status, requested_at,
                                      processed_at, admin_comment
                                 FROM access_requests WHERE user_id = %s
                                ORDER BY requested_at, id""", (subject_id,))
    ]

    archive_history = [
        _times(r, "performed_at")
        for r in _rows(cur, """SELECT id, performed_at, entity_type, entity_id, action, reason
                                 FROM archive_history WHERE performed_by = %s
                                ORDER BY performed_at, id""", (login,))
    ]

    consents_current = [
        _times(r, "granted_at", "withdrawn_at", "updated_at")
        for r in _rows(cur, """SELECT purpose, is_granted, policy_version, granted_at,
                                      withdrawn_at, updated_at, source
                                 FROM user_consents WHERE user_id = %s
                                ORDER BY purpose""", (subject_id,))
    ]
    consents_history = [
        _times(r, "occurred_at")
        for r in _rows(cur, """SELECT purpose, action, policy_version, source, occurred_at
                                 FROM consent_events WHERE user_id = %s
                                ORDER BY occurred_at, id""", (subject_id,))
    ]

    marketing = [
        _times(r, "created_at", "processed_at")
        for r in _rows(cur, """SELECT id, campaign, status, cancel_reason, created_at, processed_at
                                 FROM marketing_outbox WHERE user_id = %s
                                ORDER BY created_at, id""", (subject_id,))
    ]
    analytics = [
        _times(r, "occurred_at")
        for r in _rows(cur, """SELECT event_name, occurred_at FROM analytics_events
                                WHERE user_id = %s ORDER BY occurred_at, id""", (subject_id,))
    ]

    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": now_utc_iso(),
            "timezone": "UTC",
            "subject_id": subject_id,
            "categories": ["profile", "settings", "access_requests", "activity",
                           "consents", "communications", "analytics"],
            "sources": SOURCES,
            "excluded": EXCLUDED,
        },
        "profile": profile,
        "settings": settings,
        "access_requests": access_requests,
        "activity": {"archive_history": archive_history},
        "consents": {"current": consents_current, "history": consents_history},
        "communications": {"marketing_emails": marketing},
        "analytics": {"events": analytics},
    }


def section_counts(doc: dict) -> dict:
    """Лічильники записів — безпечно для журналу й аудиту (без значень)."""
    return {
        "access_requests": len(doc["access_requests"]),
        "archive_history": len(doc["activity"]["archive_history"]),
        "consents": len(doc["consents"]["current"]),
        "consent_events": len(doc["consents"]["history"]),
        "marketing_emails": len(doc["communications"]["marketing_emails"]),
        "analytics_events": len(doc["analytics"]["events"]),
        "settings": int(doc["settings"] is not None),
    }
