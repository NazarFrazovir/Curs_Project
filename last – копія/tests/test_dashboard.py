"""Характеризаційні тести головної сторінки та глобальних значень шаблонів.

Підроблюється пул з'єднань (db.POOL), тому тести працюють і з вихідним кодом,
і з відрефакторованим: фіксують ПОВЕДІНКУ, а не внутрішню структуру.
"""
import pytest
from flask import template_rendered

import db
from app import create_app


class FakeCursor:
    def __init__(self, answers, fail):
        self.answers, self.fail, self._result, self.description = answers, fail, [], None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if self.fail:
            raise RuntimeError("db down")
        for marker, (cols, rows) in self.answers.items():
            if marker in sql:
                self.description = [(c,) for c in cols]
                self._result = rows
                return
        self.description, self._result = [("x",)], []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeConn:
    def __init__(self, answers, fail):
        self.answers, self.fail = answers, fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return FakeCursor(self.answers, self.fail)


class FakePool:
    def __init__(self, answers=None, fail=False):
        self.answers, self.fail = answers or {}, fail

    def getconn(self):
        return FakeConn(self.answers, self.fail)

    def putconn(self, conn):
        pass


ANSWERS = {
    "FROM suppliers": (["c"], [(3,)]),
    "FROM customers": (["c"], [(5,)]),
    "FROM products  WHERE": (["c"], [(7,)]),
    "FROM stock_movements WHERE is_canceled=false": (["c"], [(11,)]),
    "SUM(b.balance_qty * p.sale_price)": (["v"], [(1234.5,)]),
    "FROM stock_movements m": (["id", "product_name"], [(1, "Цемент"), (2, "Пісок")]),
    "WHERE balance_qty <= 5": (["product", "balance_qty"], [("Цвяхи", 2)]),
    "FROM archive_history": (["entity_type", "action"], [("product", "archive")]),
    "FROM access_requests": (["c"], [(4,)]),
}


@pytest.fixture
def make_client(monkeypatch):
    def _make(pool, role=None):
        monkeypatch.setattr(db, "POOL", pool)
        client = create_app().test_client()
        if role:
            with client.session_transaction() as s:
                s["user"] = {"login": "u", "role": role}
        return client
    return _make


def render(client, url="/"):
    captured = []
    app = client.application
    template_rendered.connect(lambda sender, template, context, **kw: captured.append((template.name, context)), app, weak=False)
    resp = client.get(url)
    return resp, captured


def test_anonymous_is_redirected_to_login(make_client):
    resp = make_client(FakePool(ANSWERS)).get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dashboard_collects_stats_and_lists(make_client):
    resp, captured = render(make_client(FakePool(ANSWERS), role="Operator"))
    ctx = dict(captured)["dashboard.html"]
    assert resp.status_code == 200
    assert ctx["stats"] == {"suppliers": 3, "customers": 5, "products": 7,
                            "moves": 11, "stock_value": 1234.5}
    assert [m["product_name"] for m in ctx["recent_moves"]] == ["Цемент", "Пісок"]
    assert ctx["low_stock"] == [{"product": "Цвяхи", "balance_qty": 2}]
    assert ctx["recent_archives"] == [{"entity_type": "product", "action": "archive"}]


def test_dashboard_degrades_to_zeros_when_db_fails(make_client):
    resp, captured = render(make_client(FakePool(fail=True), role="Operator"))
    ctx = dict(captured)["dashboard.html"]
    assert resp.status_code == 200
    assert ctx["stats"] == {"suppliers": 0, "customers": 0, "products": 0, "moves": 0}
    assert "stock_value" not in ctx["stats"]
    assert ctx["recent_moves"] == ctx["low_stock"] == ctx["recent_archives"] == []


def test_pending_requests_visible_only_for_admin(make_client):
    _, admin = render(make_client(FakePool(ANSWERS), role="Admin"))
    _, oper = render(make_client(FakePool(ANSWERS), role="Operator"))
    assert dict(admin)["dashboard.html"]["pending_requests"] == 4
    assert dict(oper)["dashboard.html"]["pending_requests"] == 0


def test_pending_requests_zero_when_db_fails_for_admin(make_client):
    _, captured = render(make_client(FakePool(fail=True), role="Admin"))
    assert dict(captured)["dashboard.html"]["pending_requests"] == 0
