"""ЛР5: тести, написані за результатами мутаційного аналізу (mutmut).

Базові тести test_resilience.py давали Line Coverage 87.5 %, але Mutation Score лише 49.7 %:
виживали мутанти, які ламають реальну поведінку, наприклад
  * jitter random.uniform(0, delay/2) -> (0, delay/3)        — межі паузи не перевірялись;
  * cache_age_s = now - ts -> now + ts                       — вік кешу не перевірявся;
  * значення за замовчуванням з env (RETRY_ATTEMPTS, RETRY_BASE_DELAY) не використовувались;
  * _query_balance не виконувався жодним тестом (no tests).
Кожен тест нижче фіксує конкретний контракт, а не лише «рядок виконався».
"""
import logging
from unittest.mock import MagicMock, Mock

import psycopg2

import api
import resilience
from resilience import backoff_delay, call_with_retry

DB_DOWN = psycopg2.OperationalError("server closed the connection unexpectedly")


# ---------- backoff: точні межі equal jitter ----------

def test_backoff_lower_bound_is_half_of_delay(monkeypatch):
    monkeypatch.setattr(resilience.random, "uniform", lambda a, b: a)
    assert backoff_delay(1, base_delay=0.1, max_delay=1.0) == 0.05
    assert backoff_delay(3, base_delay=0.1, max_delay=1.0) == 0.2


def test_backoff_upper_bound_is_full_delay(monkeypatch):
    monkeypatch.setattr(resilience.random, "uniform", lambda a, b: b)
    assert backoff_delay(1, base_delay=0.1, max_delay=1.0) == 0.1
    assert backoff_delay(2, base_delay=0.1, max_delay=1.0) == 0.2
    assert backoff_delay(10, base_delay=0.1, max_delay=1.0) == 1.0   # cap


def test_backoff_uses_env_defaults(monkeypatch):
    monkeypatch.setattr(resilience.random, "uniform", lambda a, b: b)
    monkeypatch.setattr(resilience, "RETRY_BASE_DELAY", 0.4)
    monkeypatch.setattr(resilience, "RETRY_MAX_DELAY", 0.5)
    assert backoff_delay(1) == 0.4
    assert backoff_delay(2) == 0.5          # 0.8 обрізано до max


def test_backoff_explicit_args_override_env(monkeypatch):
    # явні аргументи мають пріоритет над env (значення відмінні від дефолтних 0.1 / 1.0)
    monkeypatch.setattr(resilience.random, "uniform", lambda a, b: b)
    assert backoff_delay(1, base_delay=0.2, max_delay=5.0) == 0.2
    assert backoff_delay(2, base_delay=0.1, max_delay=0.15) == 0.15


# ---------- retry: кількість спроб, паузи, журнал ----------

def test_retry_explicit_attempts_override_env():
    func = Mock(side_effect=DB_DOWN)
    try:
        call_with_retry(func, attempts=2, sleep=Mock())
    except psycopg2.OperationalError:
        pass
    assert func.call_count == 2          # дефолт RETRY_ATTEMPTS = 3 не застосовується

def test_retry_uses_env_attempts_by_default(monkeypatch):
    monkeypatch.setattr(resilience, "RETRY_ATTEMPTS", 2)
    func = Mock(side_effect=DB_DOWN)
    try:
        call_with_retry(func, sleep=Mock())
    except psycopg2.OperationalError:
        pass
    assert func.call_count == 2


def test_retry_sleeps_with_backoff_delays(monkeypatch):
    monkeypatch.setattr(resilience, "backoff_delay", lambda attempt: attempt * 0.01)
    sleep = Mock()
    func = Mock(side_effect=[DB_DOWN, DB_DOWN, "ok"])
    assert call_with_retry(func, attempts=3, sleep=sleep) == "ok"
    assert [c.args[0] for c in sleep.call_args_list] == [0.01, 0.02]


def test_retry_success_on_first_try_does_not_sleep():
    sleep = Mock()
    assert call_with_retry(lambda: 42, attempts=3, sleep=sleep) == 42
    sleep.assert_not_called()


def test_retry_logs_each_attempt_and_final_failure(monkeypatch, caplog):
    monkeypatch.setattr(resilience, "backoff_delay", lambda attempt: 0.25)
    with caplog.at_level(logging.WARNING, logger="resilience"):
        try:
            call_with_retry(Mock(side_effect=DB_DOWN), attempts=3, sleep=Mock())
        except psycopg2.OperationalError:
            pass
    msgs = [r.getMessage() for r in caplog.records]
    assert "DB call failed (attempt 1/3): server closed the connection unexpectedly; retry in 0.25s" in msgs
    assert "DB call failed (attempt 2/3): server closed the connection unexpectedly; retry in 0.25s" in msgs
    assert msgs[-1] == "DB call failed after 3 attempts: server closed the connection unexpectedly"
    assert caplog.records[-1].levelno == logging.ERROR


# ---------- /api/balance: контракт деградації ----------

def test_stale_cache_reports_its_age(client, monkeypatch):
    monkeypatch.setattr(api.time, "time", lambda: 1000.0)
    api._cache.update(items=[{"product_id": 1}], ts=970.0)
    monkeypatch.setattr(api, "_query_balance", Mock(side_effect=DB_DOWN))
    resp = client.get("/api/balance")
    assert resp.get_json() == {"status": "degraded", "degraded": True, "source": "cache",
                               "cache_age_s": 30, "items": [{"product_id": 1}]}
    assert resp.headers["Warning"] == '110 - "Response is stale"'


def test_unavailable_response_contract(client, monkeypatch):
    monkeypatch.setattr(api, "_query_balance", Mock(side_effect=DB_DOWN))
    resp = client.get("/api/balance")
    assert resp.status_code == 503
    assert resp.get_json() == {
        "status": "unavailable", "degraded": True, "items": [],
        "message": "Дані про залишки тимчасово недоступні, спробуйте пізніше"}


def test_fallback_is_logged_with_cause(client, monkeypatch, caplog):
    monkeypatch.setattr(api, "_query_balance", Mock(side_effect=DB_DOWN))
    with caplog.at_level(logging.WARNING):
        client.get("/api/balance")
    assert ("FALLBACK /api/balance: database unavailable after retries "
            "(server closed the connection unexpectedly)") in caplog.text


def test_successful_response_refreshes_cache(client, monkeypatch):
    monkeypatch.setattr(api.time, "time", lambda: 500.0)
    monkeypatch.setattr(api, "_query_balance", Mock(return_value=[{"product_id": 7}]))
    client.get("/api/balance")
    assert api._cache == {"items": [{"product_id": 7}], "ts": 500.0}


# ---------- _query_balance: SQL і перетворення типів ----------

def _fake_db(monkeypatch, rows):
    cur = MagicMock()
    cur.description = [Mock(), Mock()]
    cur.description[0].name, cur.description[1].name = "product", "balance_qty"
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    monkeypatch.setattr(api, "get_conn", lambda: ctx)
    return cur


def test_query_balance_maps_rows_and_converts_decimal(monkeypatch):
    from decimal import Decimal
    cur = _fake_db(monkeypatch, [("Цемент", Decimal("40.50"))])
    result = api._query_balance()
    assert result == [{"product": "Цемент", "balance_qty": 40.5}]
    assert isinstance(result[0]["balance_qty"], float)
    executed = [c.args[0] for c in cur.execute.call_args_list]
    assert executed[0] == "SET search_path TO app, public;"
    assert executed[1] == api.BALANCE_SQL
