"""Завдання 2. Right of Access / Personal Data Export — інтеграційні тести з PostgreSQL."""
import logging

from privacy.consent import PURPOSES

EXPECTED_SECTIONS = {"meta", "profile", "settings", "access_requests", "activity",
                     "consents", "communications", "analytics"}
# поля, яких не може бути в експорті ніде, на жодному рівні вкладеності
FORBIDDEN_KEYS = {"password", "password_hash", "reset_token", "token", "account_status",
                  "processed_by", "correlation_id", "actor_ref", "security_answer"}


def all_keys(obj) -> set:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(all_keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(all_keys(v) for v in obj)) if obj else set()
    return set()


def fill_optional_sources(client, user):
    """Дані в усіх джерелах: згоди, історія згод, черга листів, аналітика."""
    for code, purpose in PURPOSES.items():
        r = client.post(f"/api/users/{user.id}/consents/{code}/grant",
                        json={"policy_version": purpose.policy_version, "source": "web_settings"})
        assert r.status_code == 200
    assert client.post(f"/api/users/{user.id}/marketing-email",
                       json={"campaign": "autumn-sale"}).status_code == 202
    assert client.post(f"/api/users/{user.id}/analytics-events",
                       json={"event": "page.view"}).status_code == 202


def test_export_aggregates_every_source_with_control_values(make_user, login_as):
    user = make_user()
    client = login_as(user)
    fill_optional_sources(client, user)

    resp = client.get(f"/api/users/{user.id}/personal-data")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    doc = resp.get_json()

    assert set(doc) == EXPECTED_SECTIONS
    meta = doc["meta"]
    assert meta["schema_version"] == "1.0" and meta["timezone"] == "UTC"
    assert meta["generated_at"].endswith("Z")
    assert meta["subject_id"] == user.id
    assert meta["request_id"] == resp.headers["X-Request-ID"]
    assert set(meta["sources"]) >= {"profile", "settings", "consents.history"}

    profile = doc["profile"]
    assert (profile["login"], profile["email"], profile["phone"], profile["full_name"]) == \
           (user.login, user.email, user.phone, user.full_name)
    assert profile["last_login_at"].endswith("Z")
    assert doc["settings"]["theme"] == "light"
    assert doc["settings"]["default_filter"] == {"supplier": "Демо-постачальник"}
    assert user.phone in doc["access_requests"][0]["message"]
    assert [a["action"] for a in doc["activity"]["archive_history"]] == ["archive", "restore"]
    assert {c["purpose"] for c in doc["consents"]["current"]} == set(PURPOSES)
    assert [e["action"] for e in doc["consents"]["history"]] == ["GRANT", "GRANT"]
    assert doc["communications"]["marketing_emails"][0]["status"] == "queued"
    assert doc["analytics"]["events"][0]["event_name"] == "page.view"


def test_export_excludes_security_sensitive_fields(make_user, login_as):
    user = make_user()
    resp = login_as(user).get(f"/api/users/{user.id}/personal-data")
    doc = resp.get_json()
    data_sections = {k: v for k, v in doc.items() if k != "meta"}

    assert not all_keys(data_sections) & FORBIDDEN_KEYS
    assert user.password not in resp.get_data(as_text=True)
    # meta.excluded документує, що саме свідомо не повертається
    excluded = {f for item in doc["meta"]["excluded"] for f in item["fields"]}
    assert "keys.password" in excluded and "access_requests.processed_by" in excluded


def test_foreign_and_missing_subject_get_identical_denial(make_user, login_as):
    owner, stranger = make_user(), make_user()
    client = login_as(stranger)

    foreign = client.get(f"/api/users/{owner.id}/personal-data")
    missing = client.get("/api/users/999999/personal-data")

    assert foreign.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.get_json().items() if k != "request_id"}  # noqa: E731
    assert strip(foreign) == strip(missing) == {"error": "not_found"}
    body = foreign.get_data(as_text=True)
    assert all(value not in body for value in owner.pii().values())


def test_export_requires_authenticated_principal(make_user, anonymous_client):
    user = make_user()
    resp = anonymous_client.get(f"/api/users/{user.id}/personal-data")
    assert resp.status_code == 401
    assert user.email not in resp.get_data(as_text=True)


def test_session_with_spoofed_role_does_not_grant_access(make_user, anonymous_client):
    """Роль береться з БД, а не з cookie: підміна role=Admin у сесії нічого не дає."""
    owner, attacker = make_user(), make_user()
    with anonymous_client.session_transaction() as s:
        s["user"] = {"login": attacker.login, "role": "Admin"}
    assert anonymous_client.get(f"/api/users/{owner.id}/personal-data").status_code == 404


def test_admin_with_explicit_permission_can_export_but_missing_id_is_404(make_user, login_as):
    owner, admin = make_user(), make_user(role="Admin")
    client = login_as(admin)
    assert client.get(f"/api/users/{owner.id}/personal-data").status_code == 200
    assert client.get("/api/users/999999/personal-data").status_code == 404


def test_schema_is_stable_when_optional_data_is_missing(make_user, login_as, sql):
    user = make_user(with_history=False)
    sql.exec("DELETE FROM user_prefs WHERE user_login = %s", (user.login,))
    doc = login_as(user).get(f"/api/users/{user.id}/personal-data").get_json()

    assert set(doc) == EXPECTED_SECTIONS
    assert doc["settings"] is None
    assert doc["access_requests"] == []
    assert doc["activity"] == {"archive_history": []}
    assert doc["consents"] == {"current": [], "history": []}
    assert doc["communications"] == {"marketing_emails": []}
    assert doc["analytics"] == {"events": []}


def test_export_writes_audit_and_logs_no_personal_data(make_user, login_as, sql, caplog):
    user = make_user()
    client = login_as(user)
    with caplog.at_level(logging.INFO):
        resp = client.get(f"/api/users/{user.id}/personal-data")
    assert resp.status_code == 200

    log_text = caplog.text
    assert "privacy.export" in log_text and f"subject=user:{user.id}" in log_text
    assert all(value not in log_text for value in user.pii().values())
    assert '"profile"' not in log_text                     # JSON експорту не логується

    audit = sql.one("""SELECT event_type, result, correlation_id FROM privacy_audit
                        WHERE subject_ref = %s ORDER BY id DESC LIMIT 1""", (f"user:{user.id}",))
    assert audit == ("EXPORT", "success", resp.headers["X-Request-ID"])
