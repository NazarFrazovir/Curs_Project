"""ЛР7: поведінка додавання та редагування руху товару (IN/OUT).

Фіксує, які саме значення йдуть у SQL INSERT/UPDATE. Саме тут видно наслідки
неконтрольованої мутації: якщо валідатор перезапише кількість у спільному словнику,
у базу піде інше число, ніж ввів оператор. БД підмінено.
"""
from decimal import Decimal

import pytest

import inventory

FORM = {"mtype": "OUT", "movement_dt": "", "product_id": "7", "qty": "30", "price": "12.50",
        "supplier_id": "3", "customer_id": "9", "agreement_id": ""}


@pytest.fixture
def db(monkeypatch):
    state = {"available": Decimal("100"), "rows": [(False,)], "executed": []}
    monkeypatch.setattr(inventory, "fetchone", lambda q, p=(): (state["available"],))
    monkeypatch.setattr(inventory, "fetchall", lambda q, p=(): state["rows"])
    monkeypatch.setattr(inventory, "execute", lambda q, p=(): state["executed"].append((q, p)))
    return state


def login(client, role="Operator"):
    with client.session_transaction() as s:
        s["user"] = {"login": "tester", "role": role}


def flashes(client):
    with client.session_transaction() as s:
        return s.get("_flashes", [])


# ---------------- додавання ----------------

def test_add_out_saves_exactly_requested_qty(client, db):
    login(client)
    resp = client.post("/movements/add", data=FORM)
    assert resp.status_code == 302
    (_, params), = db["executed"]
    # видаток: постачальника прибрано, кількість і ціна — рівно ті, що ввів оператор
    assert params == (None, "OUT", "7", None, "9", None, "30", "12.50")
    assert flashes(client) == [("ok", "Рух додано")]


def test_add_in_clears_customer(client, db):
    login(client)
    client.post("/movements/add", data={**FORM, "mtype": "IN", "qty": "5"})
    (_, params), = db["executed"]
    assert params == (None, "IN", "7", "3", None, None, "5", "12.50")


def test_add_out_rejects_shortage(client, db):
    login(client)
    db["available"] = Decimal("10")
    client.post("/movements/add", data=FORM)
    assert db["executed"] == []
    assert flashes(client) == [("error", "Недостатньо залишку. Доступно: 10, запитано: 30")]


@pytest.mark.parametrize("qty,message", [("abc", "Невірна кількість"), ("0", "Кількість має бути додатною"),
                                         ("-2", "Кількість має бути додатною")])
def test_add_rejects_bad_qty(client, db, qty, message):
    login(client)
    client.post("/movements/add", data={**FORM, "qty": qty})
    assert db["executed"] == [] and flashes(client) == [("error", message)]


def test_add_rejects_unknown_type(client, db):
    login(client)
    client.post("/movements/add", data={**FORM, "mtype": "XX"})
    assert db["executed"] == [] and flashes(client) == [("error", "Невірний тип руху")]


def test_add_denies_guest(client, db):
    login(client, "Guest")
    client.post("/movements/add", data=FORM)
    assert db["executed"] == [] and flashes(client) == [("error", "Доступ лише для оператора/адміністратора")]


# ---------------- редагування (movements_update) ----------------

def test_update_saves_exactly_requested_qty(client, db):
    login(client, "Admin")
    client.post("/movements/42/update", data={**FORM, "movement_dt": "2026-11-01T10:00"})
    (sql, params), = db["executed"]
    assert sql.strip().startswith("UPDATE stock_movements")
    assert params == ("2026-11-01T10:00", "OUT", "7", None, "9", None, "30", "12.50", 42)
    assert flashes(client) == [("ok", "Зміни збережено")]


@pytest.mark.parametrize("rows,message", [([], "Рух не знайдено"),
                                          ([(True,)], "Скасований рух редагувати не можна")])
def test_update_rejects_missing_or_canceled(client, db, rows, message):
    login(client, "Admin")
    db["rows"] = rows
    client.post("/movements/42/update", data=FORM)
    assert db["executed"] == [] and flashes(client) == [("error", message)]


def test_update_rejects_shortage(client, db):
    login(client, "Admin")
    db["available"] = Decimal("29.5")
    client.post("/movements/42/update", data=FORM)
    assert db["executed"] == []
    assert flashes(client) == [("error", "Недостатньо залишку. Доступно: 29.5, запитано: 30")]


def test_update_denies_guest(client, db):
    login(client, "Guest")
    client.post("/movements/42/update", data=FORM)
    assert db["executed"] == []
