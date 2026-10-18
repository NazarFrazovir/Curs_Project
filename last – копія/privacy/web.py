"""HTTP API privacy-механізмів (ЛР4).

Авторизація: принципал = користувач поточної сесії, перевірений у БД.
Чужий або неіснуючий subject_id -> однакова відповідь 404 {"error": "not_found"},
тож за відповіддю неможливо дізнатись, чи існує чужий профіль.
Команди, що змінюють стан, — лише POST з JSON-тілом (простий HTML-форма з чужого
сайту такий запит надіслати не може — захист від CSRF).
"""
from __future__ import annotations

import json
import re

from flask import Blueprint, Response, request, session

from . import consent as consents
from .core import (load_principal, may_act_on, security_event, subject_ref, transaction,
                   write_audit)
from .erasure import ERASURE_POLICY, ErasureFailed, SubjectNotFound, erase_subject
from .export import build_export, section_counts
from .logging_setup import get_correlation_id

bp = Blueprint("privacy", __name__, url_prefix="/api")

_CAMPAIGN_RE = re.compile(r"^[\w-]{1,64}$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")


# ---------------------------------------------------------------------------
# Відповіді
# ---------------------------------------------------------------------------
def _json(payload, status=200):
    # порядок полів фіксований контрактом (meta першою), тому без сортування ключів
    resp = Response(json.dumps(payload, ensure_ascii=False), status=status,
                    mimetype="application/json")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _error(status, code, **extra):
    return _json({"error": code, "request_id": get_correlation_id(), **extra}, status)


def _unauthenticated():
    return _error(401, "authentication_required")


def _not_found():
    return _error(404, "not_found")


def _json_body():
    """(body, None) або (None, error_response)."""
    if not request.is_json:
        return None, _error(415, "json_body_required")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, _error(400, "invalid_json")
    return body, None


def _authorize(cur, subject_id, event, permission=None):
    """Повертає (principal, None) або (None, відповідь-відмову)."""
    principal = load_principal(cur)
    if principal is None:
        security_event(event, "anonymous", subject_ref(subject_id), "unauthenticated")
        return None, _unauthenticated()
    if not may_act_on(principal, subject_id, permission):
        security_event(event, principal.ref, subject_ref(subject_id), "not_found_or_forbidden")
        return None, _not_found()
    return principal, None


def _subject_active(cur, subject_id) -> bool:
    cur.execute("SELECT 1 FROM keys WHERE id = %s AND account_status = 'active'", (subject_id,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Службове
# ---------------------------------------------------------------------------
@bp.get("/me")
def me():
    with transaction() as cur:
        principal = load_principal(cur)
    if principal is None:
        return _unauthenticated()
    return _json({"id": principal.id, "role": principal.role})


# ---------------------------------------------------------------------------
# Завдання 2. Personal Data Export
# ---------------------------------------------------------------------------
@bp.get("/users/<int:user_id>/personal-data")
def personal_data(user_id):
    with transaction() as cur:
        principal, denied = _authorize(cur, user_id, "privacy.export", "privacy.export.any")
        if denied:
            return denied
        doc = build_export(cur, user_id)
        if doc is None:
            security_event("privacy.export", principal.ref, subject_ref(user_id), "not_found_or_forbidden")
            return _not_found()
        doc["meta"]["request_id"] = get_correlation_id()
        counts = section_counts(doc)
        write_audit(cur, "EXPORT", principal.ref, subject_ref(user_id), "success", counts)
    # у журнал — лише факт і лічильники, без JSON експорту
    security_event("privacy.export", principal.ref, subject_ref(user_id), "success", sections=counts)
    return _json(doc)


# ---------------------------------------------------------------------------
# Завдання 3. Erasure / Anonymization
# ---------------------------------------------------------------------------
@bp.post("/users/<int:user_id>/anonymize")
def anonymize(user_id):
    with transaction() as cur:
        principal, denied = _authorize(cur, user_id, "privacy.erasure", "privacy.erase.any")
    if denied:
        return denied
    body, error = _json_body()
    if error:
        return error
    if body.get("confirm") is not True:
        return _error(400, "confirmation_required", hint='передайте {"confirm": true}')
    try:
        result = erase_subject(user_id, actor=principal.ref)
    except SubjectNotFound:
        return _not_found()
    except ErasureFailed:
        return _error(500, "erasure_failed")
    if principal.id == user_id:
        session.clear()  # власну сесію завершуємо одразу
    return _json({
        "status": result.status,
        "subject_id": user_id,
        "affected": result.affected,
        "request_id": get_correlation_id(),
    })


@bp.get("/privacy/erasure-policy")
def erasure_policy():
    """Політика DELETE / ANONYMIZE / RETAIN / SKIP для кожного джерела (документація)."""
    return _json({"policy": ERASURE_POLICY})


# ---------------------------------------------------------------------------
# Завдання 4. Consent Management
# ---------------------------------------------------------------------------
@bp.get("/users/<int:user_id>/consents")
def list_consents(user_id):
    with transaction() as cur:
        _, denied = _authorize(cur, user_id, "privacy.consent.read")
        if denied:
            return denied
        return _json({
            "subject_id": user_id,
            "purposes": consents.consent_state(cur, user_id),
            "history": consents.consent_history(cur, user_id),
        })


def _change_consent(user_id, purpose, action):
    body, error = _json_body()
    if error:
        return error
    source = body.get("source", "api")
    if source not in consents.API_SOURCES:
        return _error(400, "invalid_source", allowed=sorted(consents.API_SOURCES))
    with transaction() as cur:
        # згоду дає й відкликає лише сам суб'єкт — адміністратор не може зробити це за нього
        principal, denied = _authorize(cur, user_id, f"privacy.consent.{action}")
        if denied:
            return denied
        try:
            if action == "grant":
                status = consents.grant(cur, user_id, purpose, body.get("policy_version"), source)
            else:
                status = consents.revoke(cur, user_id, purpose, source)
        except consents.UnknownPurpose:
            return _error(400, "unknown_purpose", allowed=sorted(consents.PURPOSES))
        except consents.PolicyVersionMismatch as exc:
            return _error(409, "policy_version_mismatch", required_policy_version=exc.required)
        state = next(s for s in consents.consent_state(cur, user_id)
                     if s["purpose"] == purpose.upper())
    security_event(f"privacy.consent.{action}", principal.ref, subject_ref(user_id), status,
                   purpose=purpose.upper())
    return _json({"purpose": purpose.upper(), "status": status, "consent": state})


@bp.post("/users/<int:user_id>/consents/<purpose>/grant")
def grant_consent(user_id, purpose):
    return _change_consent(user_id, purpose, "grant")


@bp.post("/users/<int:user_id>/consents/<purpose>/revoke")
def revoke_consent(user_id, purpose):
    return _change_consent(user_id, purpose, "revoke")


def _decision_response(decision, created_key, created_id):
    if decision.allowed:
        return _json({"decision": "ALLOW", "reason": decision.reason, created_key: created_id}, 202)
    return _json({"decision": "DENY", "reason": decision.reason, "purpose": decision.purpose}, 403)


@bp.post("/users/<int:user_id>/marketing-email")
def marketing_email(user_id):
    """Залежна дія: постановка маркетингового листа в чергу."""
    body, error = _json_body()
    if error:
        return error
    campaign = str(body.get("campaign", "autumn-sale"))
    if not _CAMPAIGN_RE.match(campaign):
        return _error(400, "invalid_campaign")
    with transaction() as cur:
        principal, denied = _authorize(cur, user_id, "marketing.enqueue", "marketing.send")
        if denied:
            return denied
        if not _subject_active(cur, user_id):
            return _not_found()
        decision, outbox_id = consents.enqueue_marketing_email(cur, user_id, campaign)
    security_event("marketing.enqueue", principal.ref, subject_ref(user_id), decision.outcome,
                   reason=decision.reason)
    return _decision_response(decision, "outbox_id", outbox_id)


@bp.post("/users/<int:user_id>/analytics-events")
def analytics_event(user_id):
    """Залежна дія: запис необов'язкової аналітики."""
    body, error = _json_body()
    if error:
        return error
    event_name = str(body.get("event", ""))
    if not _EVENT_RE.match(event_name):
        return _error(400, "invalid_event")
    with transaction() as cur:
        principal, denied = _authorize(cur, user_id, "analytics.record")
        if denied:
            return denied
        decision, event_id = consents.record_optional_analytics(cur, user_id, event_name)
    security_event("analytics.record", principal.ref, subject_ref(user_id), decision.outcome,
                   reason=decision.reason)
    return _decision_response(decision, "event_id", event_id)


@bp.post("/marketing/dispatch")
def marketing_dispatch():
    """Ручний запуск фонової задачі відправлення черги (Admin/Operator)."""
    _, error = _json_body()
    if error:
        return error
    with transaction() as cur:
        principal = load_principal(cur)
        if principal is None:
            return _unauthenticated()
        if not principal.has("marketing.send"):
            return _error(403, "forbidden")
        stats = consents.dispatch_marketing_outbox(cur)
    security_event("marketing.dispatch", principal.ref, "outbox", "success", **stats)
    return _json({"status": "done", **stats})
