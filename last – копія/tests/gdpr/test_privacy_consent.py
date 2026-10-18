"""Завдання 4. Consent Management Engine — інтеграційні тести сценаріїв і Policy Gate."""
import psycopg2
import pytest

from privacy import consent
from privacy.consent import PURPOSES, Purpose
from privacy.core import transaction

MARKETING = "MARKETING_EMAIL"
ANALYTICS = "OPTIONAL_ANALYTICS"


def grant(client, user, purpose=MARKETING, version=None, source="web_settings"):
    version = version or getattr(PURPOSES.get(purpose), "policy_version", "2026-10-01")
    return client.post(f"/api/users/{user.id}/consents/{purpose}/grant",
                       json={"policy_version": version, "source": source})


def revoke(client, user, purpose=MARKETING, source="web_settings"):
    return client.post(f"/api/users/{user.id}/consents/{purpose}/revoke", json={"source": source})


def send_marketing(client, user):
    return client.post(f"/api/users/{user.id}/marketing-email", json={"campaign": "autumn-sale"})


def outbox_count(sql, user):
    return sql.value("SELECT COUNT(*) FROM marketing_outbox WHERE user_id = %s", (user.id,))


def bump_policy(monkeypatch, purpose, version="2027-01-01"):
    old = PURPOSES[purpose]
    monkeypatch.setitem(PURPOSES, purpose, Purpose(old.code, version, old.description))


def test_grant_allow_revoke_deny_scenario(make_user, login_as, sql):
    """Сценарій захисту: DENY -> GRANT -> ALLOW -> REVOKE -> DENY без побічного ефекту."""
    user = make_user()
    client = login_as(user)

    # 0. початковий стан: згоди немає -> DENY, лист не створено
    r = send_marketing(client, user)
    assert r.status_code == 403 and r.get_json() == {
        "decision": "DENY", "reason": "no_consent", "purpose": MARKETING}
    assert outbox_count(sql, user) == 0

    # 1. GRANT для конкретної мети
    r = grant(client, user)
    assert r.status_code == 200 and r.get_json()["status"] == "granted"
    assert r.get_json()["consent"]["decision"] == "ALLOW"

    # 2. дозволена дія з фіксованим побічним ефектом
    r = send_marketing(client, user)
    assert r.status_code == 202 and r.get_json()["decision"] == "ALLOW"
    outbox_id = r.get_json()["outbox_id"]
    assert outbox_count(sql, user) == 1

    # 3. REVOKE
    r = revoke(client, user)
    assert r.status_code == 200 and r.get_json()["status"] == "revoked"

    # 4. та сама дія -> DENY, нових записів немає; поставлений лист скасовано
    r = send_marketing(client, user)
    assert r.status_code == 403 and r.get_json()["reason"] == "consent_withdrawn"
    assert outbox_count(sql, user) == 1
    assert sql.one("SELECT status, cancel_reason FROM marketing_outbox WHERE id = %s",
                   (outbox_id,)) == ("cancelled", "consent_withdrawn")

    # доказ: хто, коли, яку версію політики, через який канал
    events = sql.all("""SELECT action, policy_version, source, occurred_at IS NOT NULL
                          FROM consent_events WHERE user_id = %s ORDER BY id""", (user.id,))
    version = PURPOSES[MARKETING].policy_version
    assert events == [("GRANT", version, "web_settings", True), ("REVOKE", version, "web_settings", True)]
    granted_at, withdrawn_at, is_granted = sql.one(
        "SELECT granted_at, withdrawn_at, is_granted FROM user_consents WHERE user_id = %s AND purpose = %s",
        (user.id, MARKETING))
    assert is_granted is False and withdrawn_at >= granted_at


def test_consent_for_one_purpose_does_not_allow_another(make_user, login_as, sql):
    user = make_user()
    client = login_as(user)
    assert grant(client, user, MARKETING).status_code == 200

    r = client.post(f"/api/users/{user.id}/analytics-events", json={"event": "page.view"})
    assert r.status_code == 403 and r.get_json()["reason"] == "no_consent"
    assert sql.value("SELECT COUNT(*) FROM analytics_events WHERE user_id = %s", (user.id,)) == 0
    assert send_marketing(client, user).status_code == 202

    # і навпаки: відкликання аналітики не зачіпає маркетинг
    assert grant(client, user, ANALYTICS).status_code == 200
    assert revoke(client, user, ANALYTICS).status_code == 200
    assert send_marketing(client, user).status_code == 202


def test_grant_and_revoke_are_idempotent(make_user, login_as, sql):
    user = make_user()
    client = login_as(user)
    events = lambda: sql.value("SELECT COUNT(*) FROM consent_events WHERE user_id = %s", (user.id,))  # noqa: E731

    assert revoke(client, user).get_json()["status"] == "unchanged"   # нічого відкликати
    assert events() == 0
    assert grant(client, user).get_json()["status"] == "granted"
    assert grant(client, user).get_json()["status"] == "unchanged"
    assert events() == 1
    assert revoke(client, user).get_json()["status"] == "revoked"
    assert revoke(client, user).get_json()["status"] == "unchanged"
    assert events() == 2
    assert sql.value("SELECT COUNT(*) FROM user_consents WHERE user_id = %s", (user.id,)) == 1


def test_new_policy_version_invalidates_old_consent(make_user, login_as, monkeypatch):
    user = make_user()
    client = login_as(user)
    old_version = PURPOSES[MARKETING].policy_version
    assert grant(client, user).status_code == 200

    bump_policy(monkeypatch, MARKETING)
    r = send_marketing(client, user)
    assert r.status_code == 403 and r.get_json()["reason"] == "policy_version_outdated"
    # погодитись на стару версію вже не можна — клієнт отримує актуальну
    r = grant(client, user, version=old_version)
    assert r.status_code == 409 and r.get_json()["required_policy_version"] == "2027-01-01"
    assert grant(client, user, version="2027-01-01").get_json()["status"] == "granted"
    assert send_marketing(client, user).status_code == 202


def test_background_job_rechecks_consent_before_sending(make_user, login_as, sql, monkeypatch):
    allowed_user, stale_user = make_user(), make_user()
    for u in (allowed_user, stale_user):
        c = login_as(u)
        assert grant(c, u).status_code == 200
        assert send_marketing(c, u).status_code == 202
    # stale_user погодився на версію, яку потім замінили; лист уже в черзі
    sql.exec("UPDATE user_consents SET policy_version = '2020-01-01' WHERE user_id = %s", (stale_user.id,))

    sent_to = []
    with transaction() as cur:
        consent.dispatch_marketing_outbox(cur, sender=lambda email, campaign: sent_to.append(email))

    assert allowed_user.email in sent_to and stale_user.email not in sent_to
    status = lambda u: sql.one("SELECT status, cancel_reason FROM marketing_outbox WHERE user_id = %s", (u.id,))  # noqa: E731
    assert status(allowed_user) == ("sent", None)
    assert status(stale_user) == ("cancelled", "policy_version_outdated")


def test_dispatch_endpoint_requires_permission(make_user, login_as):
    assert login_as(make_user()).post("/api/marketing/dispatch", json={}).status_code == 403
    r = login_as(make_user(role="Operator")).post("/api/marketing/dispatch", json={})
    assert r.status_code == 200 and {"sent", "cancelled"} <= set(r.get_json())


def test_consent_is_not_a_universal_flag(make_user, login_as):
    """Без жодної згоди системні функції працюють: Gate стоїть лише перед optional-операціями."""
    user = make_user()
    client = login_as(user)
    assert client.get("/api/me").status_code == 200
    assert client.get(f"/api/users/{user.id}/personal-data").status_code == 200
    assert client.get("/").status_code == 200


def test_consent_commands_are_authorized_and_validated(make_user, login_as, anonymous_client):
    owner, stranger, admin = make_user(), make_user(), make_user(role="Admin")
    assert grant(login_as(stranger), owner).status_code == 404
    assert grant(login_as(admin), owner).status_code == 404       # навіть адмін не дає згоду за іншого
    assert grant(anonymous_client, owner).status_code == 401

    client = login_as(owner)
    assert grant(client, owner, purpose="NEWSLETTER_SPAM").status_code == 400
    assert grant(client, owner, source="ad_network").status_code == 400
    r = client.post(f"/api/users/{owner.id}/consents/{MARKETING}/grant", json={})
    assert r.status_code == 409 and "required_policy_version" in r.get_json()
    assert client.post(f"/api/users/{owner.id}/consents/{MARKETING}/grant",
                       data="policy_version=x").status_code == 415


def test_consent_history_is_append_only(make_user, login_as, sql):
    user = make_user()
    assert grant(login_as(user), user).status_code == 200
    with pytest.raises(psycopg2.Error, match="append-only"):
        sql.exec("UPDATE consent_events SET action = 'REVOKE' WHERE user_id = %s", (user.id,))
    with pytest.raises(psycopg2.Error, match="append-only"):
        sql.exec("DELETE FROM consent_events WHERE user_id = %s", (user.id,))
