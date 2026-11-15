"""ЛР8: SqlMovementStore — єдине місце, яке знає, як Movement лягає в таблицю stock_movements.

Реалізує контракти StockReader, MovementRepository і MovementSource.
Зміна формату рядка Movement (як перейменування sql_params -> as_db_row у FAIL-коміті)
тепер торкається тільки цього файлу.
"""
import db
from movement import Movement
from resilience import call_with_retry

COLUMNS = ("movement_dt", "mtype", "product_id", "supplier_id",
           "customer_id", "agreement_id", "qty", "price")

INSERT_SQL = """
  INSERT INTO stock_movements(movement_dt, mtype, product_id, supplier_id,
                              customer_id, agreement_id, qty, price)
  VALUES (COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s)
"""
UPDATE_SQL = """
    UPDATE stock_movements
       SET movement_dt = COALESCE(%s::timestamptz, movement_dt),
           mtype=%s, product_id=%s, supplier_id=%s, customer_id=%s,
           agreement_id=%s, qty=%s, price=%s
     WHERE id=%s
"""
AVAILABLE_SQL = """
    SELECT COALESCE(SUM(CASE WHEN mtype='IN' THEN qty ELSE -qty END), 0)
    FROM stock_movements
    WHERE product_id=%s AND is_canceled=false
      AND (%s IS NULL OR id <> %s)
"""
STATUS_SQL = "SELECT is_canceled FROM stock_movements WHERE id=%s"
FIND_SQL = f"SELECT {', '.join(COLUMNS)} FROM stock_movements WHERE id=%s"


class SqlMovementStore:
    def __init__(self, gateway=db):
        # gateway — будь-що з fetchone/fetchall/execute (модуль db або тестовий дублер)
        self._db = gateway

    def available_qty(self, product_id, exclude_id=None):
        row = self._db.fetchone(AVAILABLE_SQL, (product_id, exclude_id, exclude_id))
        return row[0] if row else 0

    def edit_error(self, rid):
        rows = self._db.fetchall(STATUS_SQL, (rid,))
        if not rows:
            return 'Рух не знайдено'
        return 'Скасований рух редагувати не можна' if rows[0][0] else None

    def insert(self, movement):
        call_with_retry(lambda: self._db.execute(INSERT_SQL, movement.as_db_row()))

    def update(self, rid, movement):
        call_with_retry(lambda: self._db.execute(UPDATE_SQL, (*movement.as_db_row(), rid)))

    def find(self, rid):
        row = self._db.fetchone(FIND_SQL, (rid,))
        if not row:
            return None
        return Movement.from_form({name: _text(value) for name, value in zip(COLUMNS, row)})


def _text(value):
    return None if value is None else str(value)
