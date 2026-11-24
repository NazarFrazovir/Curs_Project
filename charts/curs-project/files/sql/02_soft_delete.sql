-- 02_soft_delete.sql
SET search_path TO app, public;

ALTER TABLE suppliers  ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE suppliers  ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE suppliers  ADD COLUMN IF NOT EXISTS archived_by text;
ALTER TABLE suppliers  ADD COLUMN IF NOT EXISTS archive_reason text;

ALTER TABLE customers  ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE customers  ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE customers  ADD COLUMN IF NOT EXISTS archived_by text;
ALTER TABLE customers  ADD COLUMN IF NOT EXISTS archive_reason text;

ALTER TABLE products   ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE products   ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE products   ADD COLUMN IF NOT EXISTS archived_by text;
ALTER TABLE products   ADD COLUMN IF NOT EXISTS archive_reason text;

ALTER TABLE agreements ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE agreements ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE agreements ADD COLUMN IF NOT EXISTS archived_by text;
ALTER TABLE agreements ADD COLUMN IF NOT EXISTS archive_reason text;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ux_suppliers_name_active' AND n.nspname='app') THEN
    EXECUTE 'CREATE UNIQUE INDEX ux_suppliers_name_active ON app.suppliers (lower(name)) WHERE is_active';
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ux_customers_name_active' AND n.nspname='app') THEN
    EXECUTE 'CREATE UNIQUE INDEX ux_customers_name_active ON app.customers (lower(name)) WHERE is_active';
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ux_products_supplier_name_active' AND n.nspname='app') THEN
    EXECUTE 'CREATE UNIQUE INDEX ux_products_supplier_name_active ON app.products (supplier_id, lower(name)) WHERE is_active';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS archive_history (
  id           SERIAL PRIMARY KEY,
  entity_type  TEXT NOT NULL CHECK (entity_type IN ('supplier','customer','product','agreement')),
  entity_id    INT NOT NULL,
  action       TEXT NOT NULL CHECK (action IN ('archive','restore')),
  actor_login  TEXT NOT NULL REFERENCES keys(login) ON DELETE SET NULL,
  reason       TEXT,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- The trigger that prevents using archived entities is added here?
-- We'll add it here to ensure order independence relative to 00_schema.
CREATE OR REPLACE FUNCTION check_entities_active() RETURNS trigger AS $$
DECLARE
  p_active boolean;
  s_active boolean;
  c_active boolean;
  a_active boolean;
BEGIN
  SELECT is_active INTO p_active FROM products WHERE id = NEW.product_id;
  IF p_active IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Product % is archived or not found', NEW.product_id;
  END IF;

  IF NEW.mtype = 'IN' THEN
    IF NEW.supplier_id IS NULL THEN
      RAISE EXCEPTION 'IN requires supplier_id';
    END IF;
    SELECT is_active INTO s_active FROM suppliers WHERE id = NEW.supplier_id;
    IF s_active IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'Supplier % is archived or not found', NEW.supplier_id;
    END IF;
  ELSIF NEW.mtype = 'OUT' THEN
    IF NEW.customer_id IS NULL THEN
      RAISE EXCEPTION 'OUT requires customer_id';
    END IF;
    SELECT is_active INTO c_active FROM customers WHERE id = NEW.customer_id;
    IF c_active IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'Customer % is archived or not found', NEW.customer_id;
    END IF;
    IF NEW.agreement_id IS NOT NULL THEN
      SELECT is_active INTO a_active FROM agreements WHERE id = NEW.agreement_id;
      IF a_active IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Agreement % is archived or not found', NEW.agreement_id;
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_entities_active ON stock_movements;
CREATE TRIGGER trg_check_entities_active
BEFORE INSERT OR UPDATE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION check_entities_active();
