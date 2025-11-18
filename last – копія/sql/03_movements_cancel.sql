-- 03_movements_cancel.sql
SET search_path TO app, public;

ALTER TABLE stock_movements
  ADD COLUMN IF NOT EXISTS is_canceled boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS canceled_at timestamptz,
  ADD COLUMN IF NOT EXISTS canceled_by text,
  ADD COLUMN IF NOT EXISTS cancel_reason text;

CREATE OR REPLACE FUNCTION forbid_update_canceled() RETURNS trigger AS $$
BEGIN
  IF OLD.is_canceled = true AND (NEW.qty IS DISTINCT FROM OLD.qty OR NEW.price IS DISTINCT FROM OLD.price OR NEW.product_id IS DISTINCT FROM OLD.product_id OR NEW.supplier_id IS DISTINCT FROM OLD.supplier_id OR NEW.customer_id IS DISTINCT FROM OLD.customer_id OR NEW.agreement_id IS DISTINCT FROM OLD.agreement_id OR NEW.mtype IS DISTINCT FROM OLD.mtype) THEN
    RAISE EXCEPTION 'Canceled movement cannot be modified';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_forbid_update_canceled ON stock_movements;
CREATE TRIGGER trg_forbid_update_canceled
BEFORE UPDATE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION forbid_update_canceled();
