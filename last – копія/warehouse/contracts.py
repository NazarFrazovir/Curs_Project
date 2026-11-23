"""ЛР8: абстрактні контракти між частинами робочого процесу руху товару.

Класи пакета залежать від цих інтерфейсів, а не один від одного напряму
(Dependency Inversion). typing.Protocol — структурна типізація: реалізації не
успадковують контракт (DIT не росте), достатньо мати потрібні методи.
@runtime_checkable дозволяє перевірити відповідність у тестах через isinstance.
"""
from typing import Optional, Protocol, runtime_checkable

from movement import Movement


@runtime_checkable
class StockReader(Protocol):
    """Залишок товару на складі."""

    def available_qty(self, product_id: str, exclude_id: Optional[int] = None): ...


@runtime_checkable
class MovementRepository(Protocol):
    """Збереження рухів."""

    def edit_error(self, rid: int) -> Optional[str]: ...

    def insert(self, movement: Movement) -> None: ...

    def update(self, rid: int, movement: Movement) -> None: ...


@runtime_checkable
class MovementSource(Protocol):
    """Читання одного руху (для документів)."""

    def find(self, rid: int) -> Optional[Movement]: ...


@runtime_checkable
class MovementRules(Protocol):
    """Бізнес-правила допустимості руху."""

    def check(self, movement: Movement, exclude_id: Optional[int] = None) -> Optional[str]: ...


@runtime_checkable
class AuditSink(Protocol):
    """Журнал аудиту операцій."""

    def record(self, action: str, movement: Movement, actor: Optional[str],
               rid: Optional[int] = None) -> None: ...


@runtime_checkable
class TableFormat(Protocol):
    """Форматування таблиці документа (CSV, локаль тощо)."""

    def render(self, header, rows) -> bytes: ...
