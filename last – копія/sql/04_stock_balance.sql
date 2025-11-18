-- 04_stock_balance.sql
SET search_path TO app, public;

-- В'юха: залишки по кожному товару (IN - OUT), ігноруючи скасовані рухи
CREATE OR REPLACE VIEW stock_balance AS
SELECT
  p.id              AS product_id,
  p.name            AS product,
  p.unit            AS unit,
  s.id              AS supplier_id,
  s.name            AS supplier,
  COALESCE(SUM(CASE WHEN m.is_canceled THEN 0
                    WHEN m.mtype = 'IN'  THEN m.qty
                    WHEN m.mtype = 'OUT' THEN -m.qty
               END), 0) AS balance_qty,
  COALESCE(SUM(CASE WHEN m.is_canceled OR m.mtype <> 'IN'  THEN 0 ELSE m.qty END), 0) AS in_qty,
  COALESCE(SUM(CASE WHEN m.is_canceled OR m.mtype <> 'OUT' THEN 0 ELSE m.qty END), 0) AS out_qty
FROM products p
JOIN suppliers s ON s.id = p.supplier_id
LEFT JOIN stock_movements m ON m.product_id = p.id
GROUP BY p.id, p.name, p.unit, s.id, s.name;

-- Тригер: забороняє OUT, якщо не вистачає залишку
CREATE OR REPLACE FUNCTION check_stock_nonnegative() RETURNS trigger AS $$
DECLARE
  base numeric;
BEGIN
  -- Дозволяємо все, що не впливає на залишок (IN або позначення як скасований)
  IF COALESCE(NEW.is_canceled, false) = true OR NEW.mtype = 'IN' THEN
    RETURN NEW;
  END IF;

  -- Базовий залишок по товару без поточного рядка (на UPDATE)
  SELECT COALESCE(SUM(CASE WHEN m.mtype='IN' THEN m.qty ELSE -m.qty END), 0)
    INTO base
  FROM stock_movements m
  WHERE m.product_id = NEW.product_id
    AND m.is_canceled = false
    AND (TG_OP <> 'UPDATE' OR m.id <> OLD.id);

  -- Перевіряємо, що після застосування нового OUT залишок не стане від’ємним
  IF base - COALESCE(NEW.qty,0) < 0 THEN
    RAISE EXCEPTION 'Недостатньо залишку для товару %, доступно: %, запитано OUT: %',
      NEW.product_id, base, NEW.qty;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_stock_nonnegative ON stock_movements;
CREATE TRIGGER trg_check_stock_nonnegative
BEFORE INSERT OR UPDATE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION check_stock_nonnegative();

-- (опційно) корисні індекси
CREATE INDEX IF NOT EXISTS ix_stock_movements_product ON stock_movements(product_id) WHERE is_canceled=false;
CREATE INDEX IF NOT EXISTS ix_stock_movements_mtype ON stock_movements(mtype) WHERE is_canceled=false;
