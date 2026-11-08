"""ЛР7: рух товару як незмінний Value Object.

До ЛР7 рух передавався змінюваним dict-ом: валідатор переписував у ньому поля
(обнуляв сторону угоди, а при «оптимізації» — навіть кількість), і ці зміни
непомітно потрапляли в SQL. Тепер:

* `Movement` — frozen dataclass: після створення жодне поле змінити не можна
  (спроба дає dataclasses.FrozenInstanceError);
* «зміна» = новий об'єкт (`dataclasses.replace`), старий лишається незмінним;
* пов'язані дані руху (тип, товар, кількість, ціна, сторони угоди) і перевірки над
  ними живуть в одному контейнері, а не розкидані по змінних методу.
"""
from dataclasses import dataclass, replace
from typing import Optional

# Тип руху -> поле сторони угоди, яке для нього не має сенсу
# (IN — прихід від постачальника, без клієнта; OUT — видаток клієнту, без постачальника)
PARTY_TO_CLEAR = {"IN": "customer_id", "OUT": "supplier_id"}

_FORM_FIELDS = ("mtype", "movement_dt", "product_id", "qty", "price",
                "supplier_id", "customer_id", "agreement_id")
_OPTIONAL_FIELDS = ("movement_dt", "supplier_id", "customer_id", "agreement_id")


@dataclass(frozen=True)
class Movement:
    mtype: Optional[str]
    movement_dt: Optional[str]
    product_id: Optional[str]
    qty: Optional[str]
    price: Optional[str]
    supplier_id: Optional[str]
    customer_id: Optional[str]
    agreement_id: Optional[str]

    @classmethod
    def from_form(cls, form) -> "Movement":
        """Рух із форми; зайва для типу сторона угоди прибирається одразу при створенні."""
        values = {name: form.get(name) for name in _FORM_FIELDS}
        values.update({name: values[name] or None for name in _OPTIONAL_FIELDS})
        raw = cls(**values)
        party = PARTY_TO_CLEAR.get(raw.mtype)
        return replace(raw, **{party: None}) if party else raw

    @property
    def known_type(self) -> bool:
        return self.mtype in PARTY_TO_CLEAR

    @property
    def is_outgoing(self) -> bool:
        return self.mtype == "OUT"

    def qty_error(self) -> Optional[str]:
        try:
            value = float(self.qty)
        except (TypeError, ValueError):
            return "Невірна кількість"
        return None if value > 0 else "Кількість має бути додатною"

    def type_error(self) -> Optional[str]:
        return None if self.known_type else "Невірний тип руху"

    def shortage_error(self, available) -> Optional[str]:
        """Помилка, якщо видаток більший за залишок. Залишок після операції — нове значення,
        а не перезапис кількості: сам рух від перевірки не змінюється."""
        remaining = float(available) - float(self.qty)
        if remaining < 0:
            return f"Недостатньо залишку. Доступно: {available}, запитано: {self.qty}"
        return None

    def sql_params(self) -> tuple:
        """Значення для INSERT/UPDATE stock_movements у порядку колонок."""
        return (self.movement_dt, self.mtype, self.product_id, self.supplier_id,
                self.customer_id, self.agreement_id, self.qty, self.price)
