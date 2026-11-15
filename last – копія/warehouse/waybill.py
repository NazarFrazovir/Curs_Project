"""ЛР8: CsvWaybill — накладна руху товару у CSV (читає рух через контракт MovementSource)."""
import csv
import io
from decimal import Decimal

from .contracts import MovementSource

FIELDS = ("movement_dt", "mtype", "product_id", "supplier_id",
          "customer_id", "agreement_id", "qty", "price")


class CsvWaybill:
    def __init__(self, source: MovementSource):
        self._source = source

    def render(self, rid):
        """(ім'я файлу, байти CSV) або None, якщо руху немає."""
        movement = self._source.find(rid)
        if movement is None:
            return None
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["Поле", "Значення"])
        writer.writerows((name, getattr(movement, name)) for name in FIELDS)
        writer.writerow(["total", total(movement)])
        return f"waybill_{rid}.csv", out.getvalue().encode("utf-8-sig")


def total(movement):
    return (Decimal(movement.qty) * Decimal(movement.price)).quantize(Decimal("0.01"))
