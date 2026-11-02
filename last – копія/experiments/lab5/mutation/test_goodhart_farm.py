"""ЛР5, Завдання 2 — АНТИПРИКЛАД «пастки Гудхарта».

Так виглядали б тести, якби KPI команди був лише Line Coverage >= 80 %.
Кожен рядок resilience.py та api.py виконується, але НІЩО не перевіряється:
немає жодного assert, а винятки «ковтаються». Coverage — високий, захист — нульовий.
НЕ запускається в CI: лежить поза tests/, використовується тільки для демонстрації.
"""
from unittest.mock import Mock

import psycopg2

import api
from resilience import backoff_delay, call_with_retry

DB_DOWN = psycopg2.OperationalError("down")


def _swallow(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception:
        pass


def test_resilience_lines():
    backoff_delay(1)
    backoff_delay(5, base_delay=0.1, max_delay=1.0)
    call_with_retry(lambda: "ok", sleep=Mock())
    _swallow(call_with_retry, Mock(side_effect=DB_DOWN), attempts=3, sleep=Mock())
    _swallow(call_with_retry, Mock(side_effect=ValueError()), sleep=Mock())


def test_api_lines(client, monkeypatch):
    monkeypatch.setattr(api, "_query_balance", Mock(return_value=[]))
    client.get("/api/balance")                      # успіх + наповнення кешу
    monkeypatch.setattr(api, "_query_balance", Mock(side_effect=DB_DOWN))
    client.get("/api/balance")                      # fallback з кешу
    api._cache.update(items=None, ts=None)
    client.get("/api/balance")                      # 503


def test_query_balance_lines(monkeypatch):
    # «покриваємо» SQL-функцію фейковим курсором, нічого не перевіряючи
    cur = Mock()
    cur.description = [Mock(name="c")]
    cur.fetchall.return_value = []
    conn = Mock()
    conn.cursor.return_value.__enter__ = Mock(return_value=cur)
    conn.cursor.return_value.__exit__ = Mock(return_value=False)
    ctx = Mock()
    ctx.__enter__ = Mock(return_value=conn)
    ctx.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(api, "get_conn", lambda: ctx)
    _swallow(api._query_balance)
