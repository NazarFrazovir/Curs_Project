"""ЛР8, Завд.3 (PASS): накладна через композицію замість успадкування.

Було: Document -> TabularDocument -> CsvWaybill (DIT=3, 5 перевизначень). Зміна сигнатури
в базовому класі каскадно ламала обох нащадків.
Стало: жодного успадкування. CsvWaybill делегує:
  * отримання руху — MovementSource (SqlMovementStore або тестовий дублер);
  * форматування таблиці — TableFormat (CsvTable з потрібною локаллю).
Обидві залежності впроваджуються через конструктор. Нова вимога (локаль) —
це просто інший об'єкт CsvTable, а не зміна сигнатур у ланцюжку класів.
"""
import csv
import io
import re
from decimal import Decimal

from .contracts import MovementSource, TableFormat

FIELDS = ("movement_dt", "mtype", "product_id", "supplier_id",
          "customer_id", "agreement_id", "qty", "price")
HEADER = ("Поле", "Значення")
NUMBER = re.compile(r"-?\d+\.\d+")

# локаль -> (роздільник колонок, десятковий роздільник); uk — як в українському Excel
LOCALES = {"en": (",", "."), "uk": (";", ",")}


class CsvTable:
    """Форматування таблиці у CSV (контракт TableFormat)."""

    def __init__(self, locale="en"):
        self._delimiter, self._decimal = LOCALES[locale]

    def render(self, header, rows):
        out = io.StringIO()
        writer = csv.writer(out, delimiter=self._delimiter, lineterminator="\n")
        writer.writerow(header)
        writer.writerows([(name, localized(value, self._decimal)) for name, value in rows])
        return out.getvalue().encode("utf-8-sig")


class CsvWaybill:
    """Накладна руху товару. Нічого не успадковує — лише делегує."""

    def __init__(self, source: MovementSource, table: TableFormat = None):
        self._source = source
        self._table = table or CsvTable()

    def render(self, rid):
        """(ім'я файлу, байти CSV) або None, якщо руху немає."""
        movement = self._source.find(rid)
        if movement is None:
            return None
        rows = [(name, getattr(movement, name)) for name in FIELDS] + [("total", total(movement))]
        return f"waybill_{rid}.csv", self._table.render(HEADER, rows)


def localized(value, decimal_separator):
    text = "" if value is None else str(value)
    return text.replace(".", decimal_separator) if NUMBER.fullmatch(text) else text


def total(movement):
    return (Decimal(movement.qty) * Decimal(movement.price)).quantize(Decimal("0.01"))
