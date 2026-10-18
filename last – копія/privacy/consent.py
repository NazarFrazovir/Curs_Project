"""Consent Management Engine, GDPR Art. 7 (Завдання 4).

* Згода окрема для кожної мети (purpose) і прив'язана до версії політики.
* Поточний стан — app.user_consents; доказ і історія — app.consent_events (append-only).
* ConsentPolicyGate — єдине місце перевірки. Його викликають безпосередньо перед
  залежною дією (постановка листа в чергу, відправка з черги, запис аналітики).
  Кешу немає: стан читається з БД щоразу, тому REVOKE діє негайно.
* Gate застосовується ЛИШЕ до optional-операцій. Вхід, експорт, видалення,
  складські операції від згоди не залежать.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .core import iso_utc
from .logging_setup import get_correlation_id

log = logging.getLogger("privacy.consent")


@dataclass(frozen=True)
class Purpose:
    code: str
    policy_version: str
    description: str


PURPOSES = {
    "MARKETING_EMAIL": Purpose(
        "MARKETING_EMAIL", "2026-10-01", "Маркетингові листи про акції та новинки складу"),
    "OPTIONAL_ANALYTICS": Purpose(
        "OPTIONAL_ANALYTICS", "2026-10-01", "Необов'язкова аналітика використання інтерфейсу"),
}

# Канали, через які користувач може надати/відкликати згоду через API
API_SOURCES = frozenset({"web_settings", "api", "mobile_app"})


class UnknownPurpose(ValueError):
    pass


class PolicyVersionMismatch(ValueError):
    def __init__(self, required: str):
        super().__init__(f"required policy version {required}")
        self.required = required


def get_purpose(code: str) -> Purpose:
    purpose = PURPOSES.get(str(code).upper())
    if purpose is None:
        raise UnknownPurpose(code)
    return purpose


# ---------------------------------------------------------------------------
# Policy Gate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    purpose: str

    @property
    def outcome(self) -> str:
        return "ALLOW" if self.allowed else "DENY"


class ConsentPolicyGate:
    def check(self, cur, user_id: int, purpose_code: str, lock: bool = False) -> Decision:
        """lock=True: FOR SHARE на рядок згоди до кінця транзакції — конкурентний
        REVOKE дочекається завершення дії, а не проскочить між перевіркою і дією."""
        purpose = PURPOSES.get(purpose_code)
        if purpose is None:
            return Decision(False, "unknown_purpose", purpose_code)
        cur.execute(
            "SELECT is_granted, policy_version FROM user_consents "
            "WHERE user_id = %s AND purpose = %s" + (" FOR SHARE" if lock else ""),
            (user_id, purpose.code),
        )
        row = cur.fetchone()
        if row is None:
            return Decision(False, "no_consent", purpose.code)
        is_granted, version = row
        if not is_granted:
            return Decision(False, "consent_withdrawn", purpose.code)
        if version != purpose.policy_version:
            return Decision(False, "policy_version_outdated", purpose.code)
        return Decision(True, "consent_granted", purpose.code)


GATE = ConsentPolicyGate()


# ---------------------------------------------------------------------------
# GRANT / REVOKE (ідемпотентні)
# ---------------------------------------------------------------------------
def _event(cur, user_id, purpose, action, version, source):
    cur.execute(
        """INSERT INTO consent_events (user_id, purpose, action, policy_version, source, correlation_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (user_id, purpose, action, version, source, get_correlation_id()),
    )


def grant(cur, user_id: int, purpose_code: str, policy_version: str, source: str) -> str:
    """'granted' або 'unchanged' (повторний GRANT тієї самої версії не створює подію)."""
    purpose = get_purpose(purpose_code)
    if policy_version != purpose.policy_version:
        raise PolicyVersionMismatch(purpose.policy_version)
    cur.execute(
        "SELECT is_granted, policy_version FROM user_consents "
        "WHERE user_id = %s AND purpose = %s FOR UPDATE",
        (user_id, purpose.code),
    )
    row = cur.fetchone()
    if row and row[0] and row[1] == purpose.policy_version:
        return "unchanged"
    cur.execute(
        """INSERT INTO user_consents (user_id, purpose, is_granted, policy_version,
                                      granted_at, withdrawn_at, updated_at, source)
           VALUES (%s, %s, true, %s, now(), NULL, now(), %s)
           ON CONFLICT (user_id, purpose) DO UPDATE
              SET is_granted = true, policy_version = EXCLUDED.policy_version,
                  granted_at = now(), withdrawn_at = NULL, updated_at = now(),
                  source = EXCLUDED.source""",
        (user_id, purpose.code, purpose.policy_version, source),
    )
    _event(cur, user_id, purpose.code, "GRANT", purpose.policy_version, source)
    return "granted"


def revoke(cur, user_id: int, purpose_code: str, source: str) -> str:
    """'revoked' або 'unchanged'. Відкликання не зачіпає інші мети."""
    purpose = get_purpose(purpose_code)
    cur.execute(
        "SELECT is_granted, policy_version FROM user_consents "
        "WHERE user_id = %s AND purpose = %s FOR UPDATE",
        (user_id, purpose.code),
    )
    row = cur.fetchone()
    if row is None or not row[0]:
        return "unchanged"
    cur.execute(
        """UPDATE user_consents
              SET is_granted = false, withdrawn_at = now(), updated_at = now(), source = %s
            WHERE user_id = %s AND purpose = %s""",
        (source, user_id, purpose.code),
    )
    _event(cur, user_id, purpose.code, "REVOKE", row[1], source)
    if purpose.code == "MARKETING_EMAIL":
        # інвалідація черги: уже поставлені листи не будуть відправлені
        cur.execute(
            """UPDATE marketing_outbox
                  SET status = 'cancelled', cancel_reason = 'consent_withdrawn', processed_at = now()
                WHERE user_id = %s AND status = 'queued'""",
            (user_id,),
        )
    return "revoked"


def consent_state(cur, user_id: int) -> list:
    """Стан за КОЖНОЮ відомою метою (навіть якщо запису ще немає) + фактичне рішення Gate."""
    cur.execute(
        """SELECT purpose, is_granted, policy_version, granted_at, withdrawn_at, updated_at, source
             FROM user_consents WHERE user_id = %s""",
        (user_id,),
    )
    stored = {r[0]: r for r in cur.fetchall()}
    result = []
    for code, purpose in PURPOSES.items():
        r = stored.get(code)
        decision = GATE.check(cur, user_id, code)
        result.append({
            "purpose": code,
            "description": purpose.description,
            "required_policy_version": purpose.policy_version,
            "is_granted": bool(r and r[1]),
            "policy_version": r[2] if r else None,
            "granted_at": iso_utc(r[3]) if r else None,
            "withdrawn_at": iso_utc(r[4]) if r else None,
            "updated_at": iso_utc(r[5]) if r else None,
            "source": r[6] if r else None,
            "decision": decision.outcome,
            "decision_reason": decision.reason,
        })
    return result


def consent_history(cur, user_id: int) -> list:
    cur.execute(
        """SELECT purpose, action, policy_version, source, occurred_at
             FROM consent_events WHERE user_id = %s ORDER BY occurred_at, id""",
        (user_id,),
    )
    return [{"purpose": r[0], "action": r[1], "policy_version": r[2], "source": r[3],
             "occurred_at": iso_utc(r[4])} for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Залежні операції: кожна викликає Gate безпосередньо перед побічним ефектом
# ---------------------------------------------------------------------------
def enqueue_marketing_email(cur, user_id: int, campaign: str):
    """Поставити лист у чергу. DENY -> жодного запису в marketing_outbox."""
    decision = GATE.check(cur, user_id, "MARKETING_EMAIL", lock=True)
    if not decision.allowed:
        return decision, None
    cur.execute(
        "INSERT INTO marketing_outbox (user_id, campaign) VALUES (%s, %s) RETURNING id",
        (user_id, campaign),
    )
    return decision, cur.fetchone()[0]


def record_optional_analytics(cur, user_id: int, event_name: str):
    decision = GATE.check(cur, user_id, "OPTIONAL_ANALYTICS", lock=True)
    if not decision.allowed:
        return decision, None
    cur.execute(
        "INSERT INTO analytics_events (user_id, event_name) VALUES (%s, %s) RETURNING id",
        (user_id, event_name),
    )
    return decision, cur.fetchone()[0]


def dispatch_marketing_outbox(cur, limit: int = 100, sender=None) -> dict:
    """Фонова задача відправлення. Згода перевіряється ПОВТОРНО перед кожним листом:
    між постановкою в чергу і відправленням її могли відкликати або політика
    могла оновитись (нова версія -> стара згода недійсна)."""
    cur.execute(
        """SELECT id, user_id, campaign FROM marketing_outbox
            WHERE status = 'queued' ORDER BY id
            LIMIT %s FOR UPDATE SKIP LOCKED""",
        (limit,),
    )
    stats = {"sent": 0, "cancelled": 0}
    for outbox_id, user_id, campaign in cur.fetchall():
        decision = GATE.check(cur, user_id, "MARKETING_EMAIL", lock=True)
        recipient: Optional[str] = None
        if decision.allowed:
            cur.execute("SELECT email FROM keys WHERE id = %s AND account_status = 'active'", (user_id,))
            row = cur.fetchone()
            recipient = row[0] if row else None
        if decision.allowed and recipient:
            if sender is not None:
                sender(recipient, campaign)
            cur.execute("UPDATE marketing_outbox SET status = 'sent', processed_at = now() WHERE id = %s",
                        (outbox_id,))
            stats["sent"] += 1
            log.info("marketing email sent outbox_id=%s", outbox_id)
        else:
            reason = decision.reason if not decision.allowed else "no_recipient"
            cur.execute(
                """UPDATE marketing_outbox SET status = 'cancelled', cancel_reason = %s,
                          processed_at = now() WHERE id = %s""",
                (reason, outbox_id),
            )
            stats["cancelled"] += 1
            log.info("marketing email cancelled outbox_id=%s reason=%s", outbox_id, reason)
    return stats
