"""ЛР7: Movement — незмінний Value Object. Мутація з FAIL-коміту тепер неможлива."""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from movement import Movement

FORM = {"mtype": "OUT", "movement_dt": "", "product_id": "7", "qty": "30", "price": "12.50",
        "supplier_id": "3", "customer_id": "9", "agreement_id": ""}


def test_fields_cannot_be_overwritten():
    movement = Movement.from_form(FORM)
    # саме цей рядок був «оптимізацією» у FAIL-коміті
    with pytest.raises(FrozenInstanceError):
        movement.qty = 70.0


def test_validation_does_not_change_the_movement():
    movement = Movement.from_form(FORM)
    snapshot = movement.sql_params()
    assert movement.shortage_error(Decimal("100")) is None
    assert movement.shortage_error(Decimal("10")) == "Недостатньо залишку. Доступно: 10, запитано: 30"
    assert movement.sql_params() == snapshot


def test_from_form_builds_new_object_and_keeps_form_intact():
    form = dict(FORM)
    movement = Movement.from_form(form)
    assert (movement.supplier_id, movement.customer_id) == (None, "9")   # OUT — без постачальника
    assert form == FORM                                                  # вхідні дані не змінено


def test_incoming_clears_customer():
    movement = Movement.from_form({**FORM, "mtype": "IN"})
    assert (movement.supplier_id, movement.customer_id) == ("3", None)


def test_value_semantics():
    # Value Object: рівність за значенням, а не за ідентичністю об'єкта
    assert Movement.from_form(FORM) == Movement.from_form(dict(FORM))


def test_sql_params_order():
    assert Movement.from_form(FORM).sql_params() == (None, "OUT", "7", None, "9", None, "30", "12.50")


@pytest.mark.parametrize("qty,error", [("30", None), ("abc", "Невірна кількість"), (None, "Невірна кількість"),
                                       ("0", "Кількість має бути додатною")])
def test_qty_error(qty, error):
    assert Movement.from_form({**FORM, "qty": qty}).qty_error() == error


def test_unknown_type():
    movement = Movement.from_form({**FORM, "mtype": "XX"})
    assert movement.type_error() == "Невірний тип руху"
    assert (movement.supplier_id, movement.customer_id) == ("3", "9")   # нічого не обнуляємо
