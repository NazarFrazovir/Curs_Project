"""ЛР8: пакет робочого процесу руху товару — результат декомпозиції God Object WarehouseService.

  contracts.py  — абстрактні контракти (Protocol)
  store.py      — SqlMovementStore: БД            (StockReader, MovementRepository, MovementSource)
  validator.py  — MovementValidator: правила      (MovementRules)
  audit.py      — RedactingAuditTrail: аудит      (AuditSink)
  waybill.py    — CsvWaybill: накладна CSV
  service.py    — MovementService: сценарії

Цей модуль — Composition Root: єдине місце, де конкретні класи з'єднуються між собою.
"""
from .audit import RedactingAuditTrail
from .service import MovementService
from .store import SqlMovementStore
from .validator import MovementValidator
from .waybill import CsvWaybill


def movement_service():
    store = SqlMovementStore()
    return MovementService(store, MovementValidator(store), RedactingAuditTrail())


def waybill_document():
    return CsvWaybill(SqlMovementStore())
