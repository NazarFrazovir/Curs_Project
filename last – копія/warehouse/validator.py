"""ЛР8: MovementValidator — бізнес-правила допустимості руху (контракт MovementRules)."""
from .contracts import StockReader


class MovementValidator:
    def __init__(self, stock: StockReader):
        self._stock = stock

    def check(self, movement, exclude_id=None):
        """Текст помилки або None. Рух не змінюється: Movement незмінний (ЛР7)."""
        error = movement.qty_error() or movement.type_error()
        if error or not movement.is_outgoing:
            return error
        return movement.shortage_error(self._stock.available_qty(movement.product_id, exclude_id))
