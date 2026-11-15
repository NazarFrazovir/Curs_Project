"""ЛР8: MovementService — сценарії «додати» і «змінити» рух.

Знає лише контракти (MovementRepository, MovementRules, AuditSink) — не Flask,
не SQL, не логування. Залежності впроваджуються через конструктор.
"""
from .contracts import AuditSink, MovementRepository, MovementRules


class MovementService:
    def __init__(self, store: MovementRepository, rules: MovementRules, audit: AuditSink):
        self._store = store
        self._rules = rules
        self._audit = audit

    def add(self, movement, actor):
        """None — успіх, інакше текст помилки."""
        error = self._rules.check(movement)
        if error:
            return error
        self._store.insert(movement)
        self._audit.record("movement.add", movement, actor)
        return None

    def update(self, rid, movement, actor):
        error = self._store.edit_error(rid) or self._rules.check(movement, exclude_id=rid)
        if error:
            return error
        self._store.update(rid, movement)
        self._audit.record("movement.update", movement, actor, rid=rid)
        return None
