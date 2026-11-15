"""ЛР8: компоненти пакета warehouse тестуються окремо — через підставні реалізації контрактів.

Це і є практична користь Dependency Inversion: MovementService не знає ні про БД,
ні про логування, тож для тесту достатньо простих дублерів.
"""
import inspect
import logging
from decimal import Decimal

import pytest

import warehouse
from movement import Movement
from warehouse import audit, contracts, service, store, validator, waybill

FORM = {"mtype": "OUT", "movement_dt": "", "product_id": "7", "qty": "30", "price": "12.50",
        "supplier_id": "3", "customer_id": "9", "agreement_id": ""}
MOVEMENT = Movement.from_form(FORM)


class FakeStore:
    def __init__(self, available=Decimal("100"), status=None, stored=None):
        self.available, self.status, self.stored, self.calls = available, status, stored, []

    def available_qty(self, product_id, exclude_id=None):
        return self.available

    def edit_error(self, rid):
        return self.status

    def insert(self, movement):
        self.calls.append(("insert", movement))

    def update(self, rid, movement):
        self.calls.append(("update", rid, movement))

    def find(self, rid):
        return self.stored


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, action, movement, actor, rid=None):
        self.events.append((action, actor, rid))


def make_service(**kwargs):
    fake_store, fake_audit = FakeStore(**kwargs), FakeAudit()
    svc = service.MovementService(fake_store, validator.MovementValidator(fake_store), fake_audit)
    return svc, fake_store, fake_audit


# ---------- контракти ----------

@pytest.mark.parametrize("obj,contract", [
    (store.SqlMovementStore(), contracts.StockReader),
    (store.SqlMovementStore(), contracts.MovementRepository),
    (store.SqlMovementStore(), contracts.MovementSource),
    (validator.MovementValidator(FakeStore()), contracts.MovementRules),
    (audit.RedactingAuditTrail(), contracts.AuditSink),
])
def test_implementations_satisfy_contracts(obj, contract):
    assert isinstance(obj, contract)


def test_composition_root_wires_service():
    svc = warehouse.movement_service()
    assert isinstance(svc._store, store.SqlMovementStore)
    assert isinstance(svc._rules, validator.MovementValidator)


# ---------- сценарії ----------

def test_add_inserts_and_audits():
    svc, fake_store, fake_audit = make_service()
    assert svc.add(MOVEMENT, "tester") is None
    assert fake_store.calls == [("insert", MOVEMENT)]
    assert fake_audit.events == [("movement.add", "tester", None)]


def test_add_stops_on_rule_violation():
    svc, fake_store, fake_audit = make_service(available=Decimal("10"))
    assert svc.add(MOVEMENT, "tester") == "Недостатньо залишку. Доступно: 10, запитано: 30"
    assert fake_store.calls == [] and fake_audit.events == []


def test_update_checks_status_first():
    svc, fake_store, _ = make_service(status="Рух не знайдено")
    assert svc.update(42, MOVEMENT, "tester") == "Рух не знайдено"
    assert fake_store.calls == []


def test_update_saves_and_audits_with_rid():
    svc, fake_store, fake_audit = make_service()
    assert svc.update(42, MOVEMENT, "admin") is None
    assert fake_store.calls == [("update", 42, MOVEMENT)]
    assert fake_audit.events == [("movement.update", "admin", 42)]


# ---------- окремі компоненти ----------

def test_waybill_renders_from_any_source():
    filename, payload = waybill.CsvWaybill(FakeStore(stored=MOVEMENT)).render(5)
    text = payload.decode("utf-8-sig")
    assert filename == "waybill_5.csv" and text.rstrip().endswith("total,375.00")


def test_waybill_missing_movement():
    assert waybill.CsvWaybill(FakeStore(stored=None)).render(5) is None


def test_audit_masks_and_logs(caplog):
    with caplog.at_level(logging.INFO, logger="warehouse"):
        audit.RedactingAuditTrail().record("movement.add", MOVEMENT, "tester")
    assert '"action": "movement.add"' in caplog.text and '"qty": "30"' in caplog.text


# ---------- ізоляція змін (антидот Shotgun Surgery) ----------

@pytest.mark.parametrize("module", [service, validator, audit, waybill])
def test_row_mapping_lives_only_in_store(module):
    # формат рядка БД (as_db_row) знає лише SqlMovementStore — інші класи від нього не залежать
    assert "as_db_row" not in inspect.getsource(module)
    assert "as_db_row" in inspect.getsource(store)
