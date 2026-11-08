"""ЛР6: характеризаційні тести маршрутів reports.py перед зниженням їхньої складності.

Фіксують поточну поведінку sql_console (CC 19) та overheads_add (CC 16),
щоб рефакторинг до CC <= 10 гарантовано її не змінив. БД і шаблони підмінено.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import reports


@pytest.fixture
def rendered(monkeypatch):
    calls = []

    def fake_render(template, **ctx):
        calls.append((template, ctx))
        return "rendered"

    monkeypatch.setattr(reports, "render_template", fake_render)
    return calls


@pytest.fixture
def fake_db(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [(1, "IN"), (2, "OUT")]
    cur.description = [SimpleNamespace(name="id"), SimpleNamespace(name="mtype")]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    monkeypatch.setattr(reports, "get_conn", lambda: ctx)
    return cur


def login(client, role):
    with client.session_transaction() as s:
        s["user"] = {"login": "tester", "role": role}


# ---------------- sql_console ----------------

def test_sql_console_denies_guest(client, rendered):
    login(client, "Guest")
    resp = client.get("/analytics/sql")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    assert rendered == []


def test_sql_console_without_query_shows_example(client, rendered, fake_db):
    login(client, "Operator")
    client.get("/analytics/sql?run=1")
    template, ctx = rendered[0]
    assert template == "reports/sql_console.html"
    assert ctx["sql_text"].startswith("SELECT id, movement_dt, mtype")
    assert ctx == {**ctx, "date_col": "movement_dt", "d1": None, "d2": None, "limit": "200",
                   "headers": [], "rows": [], "error": None}
    fake_db.execute.assert_not_called()


def test_sql_console_runs_wrapped_select(client, rendered, fake_db):
    login(client, "Admin")
    client.get("/analytics/sql?sql=SELECT+id,mtype+FROM+stock_movements;"
               "&date_col=+movement_dt+&d1=+2026-01-01+&d2=&limit=50")
    _, ctx = rendered[0]
    assert ctx["headers"] == ["id", "mtype"]
    assert ctx["rows"] == [(1, "IN"), (2, "OUT")]
    assert ctx["limit"] == 50 and ctx["error"] is None
    assert (ctx["date_col"], ctx["d1"], ctx["d2"]) == ("movement_dt", "2026-01-01", None)
    sqls = [c.args[0] for c in fake_db.execute.call_args_list]
    assert sqls[:2] == ["SET search_path TO app, public;", "SET LOCAL statement_timeout = 3000;"]
    assert sqls[2].startswith("SELECT * FROM (SELECT id,mtype FROM stock_movements) AS q WHERE")
    assert fake_db.execute.call_args_list[2].args[1] == ("2026-01-01", "2026-01-01", None, None)


def test_sql_console_csv_export(client, rendered, fake_db):
    login(client, "Operator")
    resp = client.get("/analytics/sql?sql=SELECT+1&format=csv")
    assert resp.headers["Content-Type"].startswith("text/csv")
    assert resp.data.decode("utf-8-sig") == "id,mtype\n1,IN\n2,OUT\n"
    assert rendered == []


def test_sql_console_rejects_non_select(client, rendered, fake_db):
    login(client, "Operator")
    client.get("/analytics/sql?sql=DELETE+FROM+products")
    _, ctx = rendered[0]
    assert ctx["error"] == "Дозволено лише SELECT або WITH (CTE)"
    assert ctx["rows"] == [] and ctx["limit"] == "200"
    fake_db.execute.assert_not_called()


def test_sql_console_db_error_is_shown(client, rendered, fake_db):
    login(client, "Operator")
    fake_db.fetchall.side_effect = RuntimeError("timeout")
    client.get("/analytics/sql?sql=SELECT+1&limit=5")
    _, ctx = rendered[0]
    assert ctx["error"] == "timeout" and ctx["limit"] == 5 and ctx["rows"] == []


# ---------------- overheads_add ----------------

@pytest.fixture
def executed(monkeypatch):
    calls = []
    monkeypatch.setattr(reports, "_exec", lambda q, p=(): calls.append(p))
    return calls


def test_overheads_add_denies_guest(client, executed):
    login(client, "Guest")
    resp = client.post("/analytics/analytics/overheads/add", data={"amount": "10"})
    assert resp.headers["Location"].endswith("/analytics/profitability")
    assert executed == []


def test_overheads_add_saves_and_keeps_period(client, executed):
    login(client, "Admin")
    resp = client.post("/analytics/analytics/overheads/add?d1=2026-01-01",
                       data={"d2": "2026-01-31", "amount": " 100.5 ", "note": "  "})
    assert executed == [("2026-01-01", "2026-01-31", 100.5, None, "tester")]
    assert resp.headers["Location"].endswith("/analytics/profitability?d1=2026-01-01&d2=2026-01-31")


def test_overheads_add_without_period(client, executed):
    login(client, "Operator")
    client.post("/analytics/analytics/overheads/add", data={"amount": "7", "note": " оренда "})
    assert executed == [("", "", 7.0, "оренда", "tester")]


def test_overheads_add_rejects_bad_amount(client, executed):
    login(client, "Admin")
    resp = client.post("/analytics/analytics/overheads/add", data={"amount": "abc", "d1": "2026-02-01"})
    assert executed == []
    assert resp.headers["Location"].endswith("/analytics/profitability?d1=2026-02-01&d2=")


# ---------------- регресія: '\\copy' у FORBIDDEN_TOKENS ----------------

def test_sanitize_select_accepts_plain_select():
    # до виправлення будь-який SELECT падав з re.error "bad escape \c"
    assert reports._sanitize_select("SELECT id FROM products;") == "SELECT id FROM products"


@pytest.mark.parametrize("sql", ["COPY products TO '/tmp/x'", "SELECT 1 FROM t; \\copy t"])
def test_sanitize_select_still_blocks_copy(sql):
    with pytest.raises(ValueError):
        reports._sanitize_select(sql)
