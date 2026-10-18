"""Right to Erasure, GDPR Art. 17 — Anonymization Workflow (Завдання 3).

Обраний механізм — АНОНІМІЗАЦІЯ, а не фізичне DELETE облікового запису: на нього
посилаються бізнес-журнали складу й історія згод, які зберігаються на визначеній
підставі. Тому рядок keys лишається як знеособлений «якір» для зовнішніх ключів.

* Новий логін — випадковий (secrets), не похідний від старого: зв'язку чи ключа,
  за яким можна відновити особу, не існує. Це анонімізація, а не псевдонімізація.
* Автор дій у бізнес-журналах замінюється на спільний системний запис
  'deleted-user' — записи різних видалених користувачів неможливо зв'язати між собою.
* Усе виконується в одній транзакції (SELECT ... FOR UPDATE); помилка на будь-якому
  кроці — повний rollback. Повторний запит — 'already_anonymized' без змін.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field

from psycopg2 import sql

from .consent import _event as _consent_event
from .core import security_event, subject_ref, transaction, write_audit

log = logging.getLogger("privacy.erasure")

NEUTRAL_ACTOR = "deleted-user"
ANON_LOGIN_PREFIX = "anon-"

# Текстові колонки, де зберігається login автора дії (частина — без FK, тому
# перелічені явно). Колонки з FK на keys(login) додатково знаходяться автоматично.
ACTOR_COLUMNS = [
    ("archive_history", "performed_by"),
    ("suppliers", "archived_by"),
    ("customers", "archived_by"),
    ("products", "archived_by"),
    ("agreements", "archived_by"),
    ("stock_movements", "canceled_by"),
    ("access_requests", "processed_by"),
    ("user_prefs", "updated_by"),
]

# Політика обробки сутностей (повертається в API і використовується у звіті)
ERASURE_POLICY = [
    {"source": "keys", "action": "ANONYMIZE",
     "reason": "якір для FK історії згод і заявок; login -> випадковий anon-*, пароль -> "
               "випадкове непридатне значення; full_name/email/phone/last_login -> NULL; роль -> Guest"},
    {"source": "user_prefs", "action": "DELETE",
     "reason": "налаштування інтерфейсу — немає підстав для зберігання"},
    {"source": "access_requests", "action": "RETAIN + ANONYMIZE",
     "reason": "історія надання прав (accountability); вільний текст message/admin_comment -> NULL"},
    {"source": "archive_history, *.archived_by, stock_movements.canceled_by, "
               "access_requests.processed_by, user_prefs.updated_by",
     "action": "RETAIN + ANONYMIZE",
     "reason": "облікові записи складу зберігаються (модельне правило: облік операцій); "
               f"автор -> нейтральний системний запис '{NEUTRAL_ACTOR}'"},
    {"source": "user_consents", "action": "RETAIN + WITHDRAW",
     "reason": "усі згоди відкликаються (source=erasure); стан лишається як доказ"},
    {"source": "consent_events", "action": "RETAIN",
     "reason": "доказ згоди (Art. 7(1)); PII не містить, посилається на знеособлений id"},
    {"source": "marketing_outbox, analytics_events", "action": "DELETE",
     "reason": "необов'язкові дані без підстав для зберігання"},
    {"source": "privacy_audit", "action": "RETAIN",
     "reason": "PII не містить за побудовою — лише id, результат, лічильники"},
    {"source": "журнали застосунку", "action": "SKIP",
     "reason": "PII у журнали не потрапляють (централізоване маскування, Завдання 1)"},
    {"source": "customers, suppliers, products, agreements, stock_movements (дані)", "action": "SKIP",
     "reason": "дані контрагентів, а не суб'єкта запиту"},
]


class SubjectNotFound(Exception):
    pass


class ErasureFailed(Exception):
    pass


@dataclass
class ErasureContext:
    subject_id: int
    login: str
    affected: dict = field(default_factory=dict)

    def count(self, key: str, n: int) -> None:
        if n:
            self.affected[key] = self.affected.get(key, 0) + n


@dataclass
class ErasureResult:
    status: str          # anonymized | already_anonymized
    affected: dict


# ---------------------------------------------------------------------------
# Кроки workflow. Кожен — окрема функція, щоб у тесті можна було змоделювати
# збій посередині й перевірити rollback.
# ---------------------------------------------------------------------------
def _existing_columns(cur) -> set:
    cur.execute("SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'app'")
    return set(cur.fetchall())


def _login_fk_columns(cur) -> set:
    """Усі колонки з FK на keys(login) — щоб не пропустити посилання, додані пізніше."""
    cur.execute("""
        SELECT src.relname, att.attname
          FROM pg_constraint c
          JOIN pg_class src      ON src.oid = c.conrelid
          JOIN pg_namespace n    ON n.oid = src.relnamespace
          JOIN pg_attribute att  ON att.attrelid = c.conrelid AND att.attnum = ANY (c.conkey)
          JOIN pg_attribute ref  ON ref.attrelid = c.confrelid AND ref.attnum = ANY (c.confkey)
         WHERE c.contype = 'f' AND n.nspname = 'app'
           AND c.confrelid = 'app.keys'::regclass AND ref.attname = 'login'
    """)
    return set(cur.fetchall())


def delete_settings(cur, ctx: ErasureContext) -> None:
    cur.execute("DELETE FROM user_prefs WHERE user_login = %s", (ctx.login,))
    ctx.count("user_prefs:deleted", cur.rowcount)


def neutralize_actor_references(cur, ctx: ErasureContext) -> None:
    existing = _existing_columns(cur)
    targets = (set(ACTOR_COLUMNS) | _login_fk_columns(cur)) - {("user_prefs", "user_login")}
    for table, column in sorted(targets):
        if (table, column) not in existing:
            continue
        cur.execute(
            sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(
                sql.Identifier("app", table), sql.Identifier(column), sql.Identifier(column)),
            (NEUTRAL_ACTOR, ctx.login),
        )
        ctx.count(f"{table}.{column}:neutralized", cur.rowcount)


def scrub_access_requests(cur, ctx: ErasureContext) -> None:
    cur.execute(
        """UPDATE access_requests SET message = NULL, admin_comment = NULL
            WHERE user_id = %s AND (message IS NOT NULL OR admin_comment IS NOT NULL)""",
        (ctx.subject_id,),
    )
    ctx.count("access_requests:free_text_removed", cur.rowcount)


def withdraw_consents(cur, ctx: ErasureContext) -> None:
    cur.execute(
        """UPDATE user_consents
              SET is_granted = false, withdrawn_at = now(), updated_at = now(), source = 'erasure'
            WHERE user_id = %s AND is_granted
        RETURNING purpose, policy_version""",
        (ctx.subject_id,),
    )
    withdrawn = cur.fetchall()
    for purpose, version in withdrawn:
        _consent_event(cur, ctx.subject_id, purpose, "REVOKE", version, "erasure")
    ctx.count("user_consents:withdrawn", len(withdrawn))


def delete_optional_data(cur, ctx: ErasureContext) -> None:
    for table in ("marketing_outbox", "analytics_events"):
        cur.execute(sql.SQL("DELETE FROM {} WHERE user_id = %s").format(sql.Identifier("app", table)),
                    (ctx.subject_id,))
        ctx.count(f"{table}:deleted", cur.rowcount)


def anonymize_account(cur, ctx: ErasureContext) -> None:
    cur.execute(
        """UPDATE keys
              SET login = %s, password = %s, role = 'Guest',
                  full_name = NULL, email = NULL, phone = NULL, last_login = NULL,
                  account_status = 'anonymized', anonymized_at = now()
            WHERE id = %s""",
        (ANON_LOGIN_PREFIX + secrets.token_hex(8), secrets.token_hex(32), ctx.subject_id),
    )
    ctx.count("keys:anonymized", cur.rowcount)


ERASURE_STEPS = [
    delete_settings,              # до зміни login: user_prefs.user_login має FK на keys(login)
    neutralize_actor_references,
    scrub_access_requests,
    withdraw_consents,
    delete_optional_data,
    anonymize_account,            # останнім: після нього старого login ніде не лишається
]


def erase_subject(subject_id: int, actor: str) -> ErasureResult:
    subject = subject_ref(subject_id)
    try:
        with transaction() as cur:
            cur.execute("SELECT login, account_status FROM keys WHERE id = %s FOR UPDATE",
                        (subject_id,))
            row = cur.fetchone()
            if row is None or row[1] == "system":
                raise SubjectNotFound(subject_id)
            if row[1] == "anonymized":
                write_audit(cur, "ERASURE", actor, subject, "noop", {"reason": "already_anonymized"})
                result = ErasureResult("already_anonymized", {})
            else:
                ctx = ErasureContext(subject_id=subject_id, login=row[0])
                for step in ERASURE_STEPS:
                    step(cur, ctx)
                write_audit(cur, "ERASURE", actor, subject, "success", ctx.affected)
                result = ErasureResult("anonymized", ctx.affected)
    except SubjectNotFound:
        raise
    except Exception as exc:
        # транзакцію вже відкочено; факт збою фіксуємо окремою транзакцією
        log.exception("erasure failed subject=%s", subject)
        try:
            with transaction() as cur:
                write_audit(cur, "ERASURE", actor, subject, "failed", {"error_type": type(exc).__name__})
        except Exception:
            log.error("could not write erasure failure audit subject=%s", subject)
        security_event("privacy.erasure", actor, subject, "failed")
        raise ErasureFailed(type(exc).__name__) from exc

    security_event("privacy.erasure", actor, subject, result.status, affected=result.affected)
    return result
