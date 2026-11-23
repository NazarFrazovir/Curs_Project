"""Нові ендпоінти: /api/stock-alerts і /api/health."""
from decimal import Decimal

import psycopg2
import pytest

import db


@pytest.fixture
def rows(monkeypatch):
    calls = {}

    def fake_fetchall(query, params=()):
        calls["params"] = params
        return [(7, "Цемент", "мішок", "БудПостач", Decimal("3"))]

    monkeypatch.setattr(db, "fetchall", fake_fetchall)
    return calls


def test_stock_alerts_default_threshold(client, rows):
    body = client.get("/api/stock-alerts").get_json()
    assert body["status"] == "ok" and body["threshold"] == 10.0 and rows["params"] == (10.0,)
    assert body["items"] == [{"product_id": 7, "product": "Цемент", "unit": "мішок",
                              "supplier": "БудПостач", "balance_qty": 3.0}]


def test_stock_alerts_custom_and_invalid_threshold(client, rows):
    assert client.get("/api/stock-alerts?below=5").get_json()["threshold"] == 5.0
    assert client.get("/api/stock-alerts?below=-1").status_code == 400
    assert client.get("/api/stock-alerts?below=abc").status_code == 400


def test_health_up(client, monkeypatch):
    monkeypatch.setattr(db, "fetchone", lambda q, p=(): (1,))
    resp = client.get("/api/health")
    assert resp.status_code == 200 and resp.get_json() == {"status": "ok", "db": "up"}


@pytest.mark.parametrize("error", [RuntimeError("no pool"), psycopg2.OperationalError("down")])
def test_health_down(client, monkeypatch, error):
    def broken(q, p=()):
        raise error
    monkeypatch.setattr(db, "fetchone", broken)
    resp = client.get("/api/health")
    assert resp.status_code == 503 and resp.get_json()["status"] == "down"
