"""Завдання 3. Right to Erasure / Anonymization — інтеграційні перевірки стану БД."""
import logging

import pytest

from privacy import erasure
from privacy.consent import PURPOSES

CONFIRM = {"confirm": True}


@pytest.fixture
def rich_user(make_user, login_as, sql):
    """Користувач, чиї дані розкидані по прямих і непрямих джерелах."""
    user = make_user()
    client = login_as(user)
    for code, purpose in PURPOSES.items():
        client.post(f"/api/users/{user.id}/consents/{code}/grant",
                    json={"policy_version": purpose.policy_version})
    client.post(f"/api/users/{user.id}/marketing-email", json={"campaign": "autumn-sale"})
    client.post(f"/api/users/{user.id}/analytics-events", json={"event": "page.view"})
    # непрямі сліди: користувач як автор дій у складських таблицях
    supplier_id = sql.value("INSERT INTO suppliers (name) VALUES (%s) RETURNING id",
                            (f"Постачальник {user.id}",))
    product_id = sql.value(
        """INSERT INTO products (supplier_id, name, unit, purchase_price, sale_price)
           VALUES (%s, %s, 'шт', 10, 15) RETURNING id""", (supplier_id, f"Товар {user.id}"))
    sql.exec("""INSERT INTO stock_movements (mtype, product_id, supplier_id, qty, price,
                                             is_canceled, canceled_at, canceled_by, cancel_reason)
                VALUES ('IN', %s, %s, 5, 10, true, now(), %s, 'помилкове введення')""",
             (product_id, supplier_id, user.login))
    sql.exec("""INSERT INTO customers (name, is_active, archived_at, archived_by)
                VALUES (%s, false, now(), %s)""", (f"Клієнт архівований {user.id}", user.login))
    # заявку ІНШОГО користувача розглядав цей користувач
    other = make_user(with_history=True)
    sql.exec("UPDATE access_requests SET processed_by = %s WHERE user_id = %s", (user.login, other.id))
    return user, client


def anonymize(client, user_id, body=CONFIRM):
    return client.post(f"/api/users/{user_id}/anonymize", json=body)


def test_pii_is_removed_from_every_source(rich_user, sql):
    user, client = rich_user
    assert sql.find_everywhere(user.pii()), "контроль: до операції PII є в БД"

    resp = anonymize(client, user.id)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "anonymized"

    assert sql.find_everywhere(user.pii()) == []      # ані в users, ані в пов'язаних таблицях
    login, email, phone, full_name, status, password = sql.one(
        "SELECT login, email, phone, full_name, account_status, password FROM keys WHERE id = %s",
        (user.id,))
    assert login.startswith("anon-") and user.login not in login
    assert (email, phone, full_name, status) == (None, None, None, "anonymized")
    assert password != user.password
    assert sql.value("SELECT COUNT(*) FROM user_prefs WHERE user_login IN (%s, %s)",
                     (user.login, login)) == 0


def test_retained_records_stay_intact_and_reports_still_work(rich_user, sql, make_user, login_as):
    user, client = rich_user
    totals_before = {t: sql.value(f"SELECT COUNT(*) FROM {t}")
                     for t in ("archive_history", "access_requests", "stock_movements", "customers")}
    events_before = sql.value("SELECT COUNT(*) FROM consent_events WHERE user_id = %s", (user.id,))

    assert anonymize(client, user.id).status_code == 200

    # бізнес-записи збережено (RETAIN), кількість не змінилась
    for table, count in totals_before.items():
        assert sql.value(f"SELECT COUNT(*) FROM {table}") == count, table
    # автор дій — нейтральний системний запис, а не випадковий логін (немає зв'язуваності)
    assert sql.value("SELECT COUNT(*) FROM archive_history WHERE performed_by = 'deleted-user'") >= 2
    assert sql.value("SELECT canceled_by FROM stock_movements WHERE cancel_reason = 'помилкове введення' "
                     "ORDER BY id DESC LIMIT 1") == "deleted-user"
    # заявка лишилась, але без вільного тексту
    assert sql.one("SELECT status, message, admin_comment FROM access_requests WHERE user_id = %s",
                   (user.id,)) == ("approved", None, None)
    # згоди відкликано, історія доповнена, а не переписана
    assert sql.value("SELECT COUNT(*) FROM user_consents WHERE user_id = %s AND is_granted", (user.id,)) == 0
    assert sql.value("SELECT COUNT(*) FROM consent_events WHERE user_id = %s", (user.id,)) == events_before + 2
    assert sql.value("SELECT COUNT(*) FROM marketing_outbox WHERE user_id = %s", (user.id,)) == 0
    # референційна цілісність: жодних «сиріт»
    orphans = sql.value("""
        SELECT (SELECT COUNT(*) FROM archive_history a LEFT JOIN keys k ON k.login = a.performed_by
                 WHERE k.login IS NULL)
             + (SELECT COUNT(*) FROM access_requests r LEFT JOIN keys k ON k.id = r.user_id
                 WHERE k.id IS NULL)
             + (SELECT COUNT(*) FROM consent_events e LEFT JOIN keys k ON k.id = e.user_id
                 WHERE k.id IS NULL)""")
    assert orphans == 0
    # звітні сторінки, що читають ці таблиці, працюють
    admin = login_as(make_user(role="Admin"))
    assert admin.get("/archive-history").status_code == 200
    assert admin.get("/").status_code == 200


def test_repeated_request_is_idempotent(rich_user, sql, make_user, login_as):
    user, client = rich_user
    assert anonymize(client, user.id).status_code == 200
    snapshot = sql.one("SELECT login, password, anonymized_at FROM keys WHERE id = %s", (user.id,))
    keys_count = sql.value("SELECT COUNT(*) FROM keys")

    # той самий клієнт: сесію вже завершено, акаунта зі старим login немає
    assert anonymize(client, user.id).status_code == 401
    # адміністратор повторює запит
    admin = login_as(make_user(role="Admin"))
    keys_count += 1
    resp = anonymize(admin, user.id)
    assert resp.status_code == 200 and resp.get_json()["status"] == "already_anonymized"
    assert sql.one("SELECT login, password, anonymized_at FROM keys WHERE id = %s", (user.id,)) == snapshot
    assert sql.value("SELECT COUNT(*) FROM keys") == keys_count       # нових профілів не створено
    assert sql.find_everywhere(user.pii()) == []                      # PII не повернулись


def test_partial_failure_rolls_back_everything(rich_user, sql, monkeypatch):
    user, client = rich_user

    def crash(cur, ctx):
        raise RuntimeError("simulated failure after half of the workflow")

    steps = list(erasure.ERASURE_STEPS)
    monkeypatch.setattr(erasure, "ERASURE_STEPS", steps[:3] + [crash] + steps[3:])

    resp = anonymize(client, user.id)
    assert resp.status_code == 500 and resp.get_json()["error"] == "erasure_failed"

    # нічого з перших трьох кроків не збереглось
    assert sql.one("SELECT login, email, account_status FROM keys WHERE id = %s", (user.id,)) == \
           (user.login, user.email, "active")
    assert sql.value("SELECT COUNT(*) FROM user_prefs WHERE user_login = %s", (user.login,)) == 1
    assert sql.value("SELECT COUNT(*) FROM archive_history WHERE performed_by = %s", (user.login,)) == 2
    assert user.phone in sql.value("SELECT message FROM access_requests WHERE user_id = %s", (user.id,))
    # факт збою зафіксовано без деталей даних
    assert sql.one("""SELECT result, details->>'error_type' FROM privacy_audit
                       WHERE subject_ref = %s AND event_type = 'ERASURE' ORDER BY id DESC LIMIT 1""",
                   (f"user:{user.id}",)) == ("failed", "RuntimeError")

    # після усунення збою workflow можна безпечно виконати повторно
    monkeypatch.setattr(erasure, "ERASURE_STEPS", steps)
    assert anonymize(client, user.id).status_code == 200
    assert sql.find_everywhere(user.pii()) == []


def test_operation_is_forbidden_for_other_actors(rich_user, make_user, login_as, anonymous_client, sql):
    user, owner_client = rich_user
    operator = login_as(make_user(role="Operator"))

    assert anonymize(operator, user.id).status_code == 404        # без розкриття існування
    assert anonymize(anonymous_client, user.id).status_code == 401
    assert owner_client.get(f"/api/users/{user.id}/anonymize").status_code == 405   # не GET
    assert anonymize(owner_client, user.id, body={}).status_code == 400            # без confirm
    assert owner_client.post(f"/api/users/{user.id}/anonymize",
                             data="confirm=true").status_code == 415               # не JSON
    assert sql.value("SELECT account_status FROM keys WHERE id = %s", (user.id,)) == "active"
    assert sql.find_everywhere({"email": user.email})


def test_audit_event_and_logs_contain_no_personal_data(rich_user, sql, caplog):
    user, client = rich_user
    with caplog.at_level(logging.INFO):
        resp = anonymize(client, user.id)
    audit = sql.one("""SELECT event_type, actor_ref, result, correlation_id, details::text
                         FROM privacy_audit WHERE subject_ref = %s AND event_type = 'ERASURE'
                        ORDER BY id DESC LIMIT 1""", (f"user:{user.id}",))
    assert audit[:4] == ("ERASURE", f"user:{user.id}", "success", resp.headers["X-Request-ID"])
    assert all(value not in audit[4] for value in user.pii().values())   # лише лічильники
    assert "keys:anonymized" in audit[4]
    assert all(value not in caplog.text for value in user.pii().values())


def test_erased_user_loses_session_and_cannot_log_in(make_user, login_as, anonymous_client):
    user = make_user()
    user_client = login_as(user)
    admin = login_as(make_user(role="Admin"))
    assert anonymize(admin, user.id).status_code == 200

    assert user_client.get("/api/me").status_code == 401          # стара cookie більше не діє
    with user_client.session_transaction() as s:
        assert "user" not in s
    anonymous_client.post("/login", data={"login": user.login, "password": user.password})
    with anonymous_client.session_transaction() as s:
        assert "user" not in s
    assert admin.get(f"/api/users/{user.id}/personal-data").status_code == 404
