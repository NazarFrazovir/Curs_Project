"""ЛР8 (Baseline): WarehouseService — увесь робочий процес руху товару в одному класі.

Логіка, що раніше була розпорошена по inventory.py (перевірки прав, читання форми,
залишок, запис у БД), movement.py (мапування в SQL), модулю логування ЛР4 (аудит
з маскуванням ПДн) і звітам (CSV), зібрана в один «зручний» сервіс.
Саме так з часом і з'являються класи-мутанти (God Object): кожна нова вимога
дописується туди, де вже «все є».
"""
import csv
import io
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from flask import Response, flash, request, session

import db
from movement import Movement
from privacy.sanitizer import redact
from resilience import call_with_retry

MOVEMENT_COLUMNS = ("movement_dt", "mtype", "product_id", "supplier_id",
                    "customer_id", "agreement_id", "qty", "price")


class WarehouseService:
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
    WAYBILL_SQL = """
        SELECT movement_dt, mtype, product_id, supplier_id, customer_id, agreement_id, qty, price
        FROM stock_movements WHERE id=%s
    """

    def __init__(self):
        self.log = logging.getLogger("warehouse")
        self.user = session.get("user") or {}
        self.last_error = None
        self.audit_events = []
        self.started = time.monotonic()

    # ---------- доступ і форма ----------
    def can_edit(self):
        return self.user.get("role") in ("Admin", "Operator")

    def read_form(self):
        return Movement.from_form(request.form)

    # ---------- склад ----------
    def available_qty(self, product_id, exclude_id=None):
        row = db.fetchone(self.AVAILABLE_SQL, (product_id, exclude_id, exclude_id))
        return row[0] if row else 0

    def validate(self, movement, exclude_id=None):
        error = movement.qty_error() or movement.type_error()
        if error or not movement.is_outgoing:
            return error
        return movement.shortage_error(self.available_qty(movement.product_id, exclude_id))

    def edit_error(self, rid):
        rows = db.fetchall("SELECT is_canceled FROM stock_movements WHERE id=%s", (rid,))
        if not rows:
            return 'Рух не знайдено'
        return 'Скасований рух редагувати не можна' if rows[0][0] else None

    # ---------- сценарії ----------
    def add_movement(self):
        if not self.can_edit():
            return self._fail('Доступ лише для оператора/адміністратора')
        movement = self.read_form()
        error = self.validate(movement)
        if error:
            return self._fail(error)
        self._write(self.INSERT_SQL, movement.sql_params())
        self.audit("movement.add", movement)
        flash('Рух додано', 'ok')
        return True

    def update_movement(self, rid):
        if not self.can_edit():
            return self._fail('Редагувати може лише оператор/адміністратор')
        movement = self.read_form()
        error = self.edit_error(rid) or self.validate(movement, exclude_id=rid)
        if error:
            return self._fail(error)
        self._write(self.UPDATE_SQL, (*movement.sql_params(), rid))
        self.audit("movement.update", movement, rid=rid)
        flash('Зміни збережено', 'ok')
        return True

    def _write(self, sql, params):
        call_with_retry(lambda: db.execute(sql, params))

    def _fail(self, message):
        self.last_error = message
        flash(message, 'error')
        return False

    # ---------- аудит (ЛР4: без ПДн у логах) ----------
    def audit(self, action, movement, rid=None):
        event = {"action": action, "rid": rid, "actor": self.user.get("login"),
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "movement": redact(asdict(movement)),
                 "params": dict(zip(MOVEMENT_COLUMNS, movement.sql_params()))}
        self.audit_events.append(event)
        self.log.info(json.dumps(event, ensure_ascii=False, default=str))

    # ---------- накладна CSV ----------
    def waybill(self, rid):
        row = db.fetchone(self.WAYBILL_SQL, (rid,))
        if not row:
            return Response("Рух не знайдено", status=404)
        movement = Movement.from_form(dict(zip(MOVEMENT_COLUMNS, map(_text, row))))
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["Поле", "Значення"])
        writer.writerows(zip(MOVEMENT_COLUMNS, movement.sql_params()))
        writer.writerow(["total", self.waybill_total(movement)])
        return Response(out.getvalue().encode("utf-8-sig"), headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f"attachment; filename=waybill_{rid}.csv"})

    def waybill_total(self, movement):
        return (Decimal(movement.qty) * Decimal(movement.price)).quantize(Decimal("0.01"))


def _text(value):
    return None if value is None else str(value)
