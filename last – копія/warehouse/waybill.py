"""ЛР8, Завд.3 (Baseline): документи руху товару через ієрархію успадкування.

    Document            — базовий «шаблонний» документ (render -> filename + encode(body))
      └ TabularDocument — документ-таблиця: заголовок, рядки, підсумок
          └ CsvWaybill  — накладна CSV: перевизначає половину логіки предків

Типовий шлях до Inheritance Hell: спільна база, від якої «зручно» успадковуватись,
і нащадки, що латають батьківську поведінку перевизначеннями.
"""
import csv
import io
from decimal import Decimal

FIELDS = ("movement_dt", "mtype", "product_id", "supplier_id",
          "customer_id", "agreement_id", "qty", "price")


class Document:
    extension = "txt"

    def __init__(self, source):
        self._source = source

    def render(self, rid, locale="uk"):
        """Template Method: (ім'я файлу, байти) або None, якщо руху немає.
        ЛР8 (FAIL): нова вимога бухгалтерії — числа за локаллю (uk: десяткова кома),
        тому базовий клас тепер передає locale у body/lines."""
        movement = self._source.find(rid)
        if movement is None:
            return None
        return self.filename(rid), self.encode(self.body(movement, locale=locale))

    def filename(self, rid):
        return f"{self.prefix()}_{rid}.{self.extension}"

    def prefix(self):
        return "document"

    def title(self):
        return "Документ руху товару"

    def body(self, movement, *, locale):
        return "\n".join([self.title(), *self.lines(movement, locale=locale)])

    def lines(self, movement, *, locale):
        return [f"{name}: {localized(getattr(movement, name), locale)}" for name in FIELDS]

    def encode(self, text):
        return text.encode("utf-8")


class TabularDocument(Document):
    def header(self):
        return ["Поле", "Значення"]

    def rows(self, movement):
        return [(name, getattr(movement, name)) for name in FIELDS]

    def footer(self, movement):
        return [("total", total(movement))]

    def lines(self, movement):                       # перевизначення Document.lines
        table = [self.header(), *self.rows(movement), *self.footer(movement)]
        return [self.join(row) for row in table]

    def join(self, cells):
        return "\t".join(map(str, cells))


class CsvWaybill(TabularDocument):
    extension = "csv"

    def prefix(self):                                # перевизначення Document.prefix
        return "waybill"

    def title(self):                                 # перевизначення Document.title
        return ""

    def body(self, movement):                        # перевизначення Document.body
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerows([self.header(), *self.rows(movement), *self.footer(movement)])
        return out.getvalue()

    def join(self, cells):                           # перевизначення TabularDocument.join
        return ",".join(map(str, cells))

    def encode(self, text):                          # перевизначення Document.encode
        return text.encode("utf-8-sig")


def localized(value, locale):
    text = "" if value is None else str(value)
    return text.replace(".", ",") if locale == "uk" else text


def total(movement):
    return (Decimal(movement.qty) * Decimal(movement.price)).quantize(Decimal("0.01"))
