"""Resilience tests: детерміновано моделюють відмову PostgreSQL через mock."""
import logging
from unittest.mock import Mock

import psycopg2
import pytest

import api
from resilience import backoff_delay, call_with_retry

DB_DOWN = psycopg2.OperationalError("server closed the connection unexpectedly")
ITEMS = [{"product_id": 1, "product": "Цемент М500", "unit": "мішок",
          "supplier": "БудПостач", "balance_qty": 40.0}]


# ---------- Механізм Retry ----------

def test_retry_recovers_after_transient_failures():
    func = Mock(side_effect=[DB_DOWN, DB_DOWN, "ok"])
    sleep = Mock()
    assert call_with_retry(func, attempts=3, sleep=sleep) == "ok"
    assert func.call_count == 3
    assert sleep.call_count == 2


def test_retry_gives_up_after_max_attempts():
    func = Mock(side_effect=DB_DOWN)
    sleep = Mock()
    with pytest.raises(psycopg2.OperationalError):
        call_with_retry(func, attempts=3, sleep=sleep)
    assert func.call_count == 3          # не більше 3 спроб — немає retry storm
    assert sleep.call_count == 2         # пауза лише між спробами


def test_non_transient_error_is_not_retried():
    func = Mock(side_effect=psycopg2.ProgrammingError("syntax error"))
    with pytest.raises(psycopg2.ProgrammingError):
        call_with_retry(func, attempts=3, sleep=Mock())
    assert func.call_count == 1


def test_backoff_grows_and_is_capped():
    for _ in range(50):
        assert 0.05 <= backoff_delay(1, base_delay=0.1, max_delay=1.0) <= 0.1
        assert 0.10 <= backoff_delay(2, base_delay=0.1, max_delay=1.0) <= 0.2
        assert 0.50 <= backoff_delay(10, base_delay=0.1, max_delay=1.0) <= 1.0


# ---------- API /api/balance ----------

def test_balance_ok_when_db_available(client, monkeypatch, caplog):
    query = Mock(return_value=ITEMS)
    monkeypatch.setattr(api, "_query_balance", query)
    with caplog.at_level(logging.WARNING):
        resp = client.get("/api/balance")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "degraded": False,
                               "source": "db", "items": ITEMS}
    assert query.call_count == 1
    assert "FALLBACK" not in caplog.text   # fallback не активувався


def test_balance_serves_stale_cache_when_db_down(client, monkeypatch, caplog):
    monkeypatch.setattr(api, "_query_balance", Mock(return_value=ITEMS))
    client.get("/api/balance")                       # наповнюємо кеш

    failing = Mock(side_effect=DB_DOWN)
    monkeypatch.setattr(api, "_query_balance", failing)
    with caplog.at_level(logging.WARNING):
        resp = client.get("/api/balance")

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["degraded"] is True
    assert body["source"] == "cache"
    assert body["items"] == ITEMS
    assert resp.headers["Warning"].startswith("110")
    assert failing.call_count == 3                   # 1 спроба + 2 повтори
    assert "FALLBACK /api/balance" in caplog.text    # діагностичний запис


def test_balance_returns_503_when_db_down_and_no_cache(client, monkeypatch):
    failing = Mock(side_effect=DB_DOWN)
    monkeypatch.setattr(api, "_query_balance", failing)
    resp = client.get("/api/balance")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    assert resp.get_json()["status"] == "unavailable"
    assert failing.call_count == 3
