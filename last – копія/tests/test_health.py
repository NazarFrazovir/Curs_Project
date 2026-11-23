def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert "version" in body


def test_readyz_unavailable_without_db(client):
    # У тестах DATABASE_URL порожній, пул не створено -> не готовий
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "unavailable"
