-- 00_schema.sql
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION CURRENT_USER;
SET search_path TO app, public;

-- Users/roles (Keys table per assignment)
CREATE TABLE IF NOT EXISTS keys (
  login TEXT PRIMARY KEY,
  password TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('Admin','Operator','Authorized','Guest'))
);

-- Suppliers, Customers
CREATE TABLE IF NOT EXISTS suppliers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  address TEXT,
  phone TEXT
);

CREATE TABLE IF NOT EXISTS customers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  address TEXT,
  phone TEXT
);

-- Products
CREATE TABLE IF NOT EXISTS products (
  id SERIAL PRIMARY KEY,
  supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  purchase_price NUMERIC(14,2) NOT NULL CHECK (purchase_price >= 0),
  sale_price NUMERIC(14,2) NOT NULL CHECK (sale_price >= 0)
);

-- Agreements
CREATE TABLE IF NOT EXISTS agreements (
  id SERIAL PRIMARY KEY,
  customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  agreement_no TEXT NOT NULL,
  agreement_dt DATE NOT NULL
);

-- Stock movements
CREATE TABLE IF NOT EXISTS stock_movements (
  id SERIAL PRIMARY KEY,
  movement_dt timestamptz NOT NULL DEFAULT now(),
  mtype TEXT NOT NULL CHECK (mtype IN ('IN','OUT')),
  product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  supplier_id INT REFERENCES suppliers(id) ON DELETE RESTRICT,
  customer_id INT REFERENCES customers(id) ON DELETE RESTRICT,
  agreement_id INT REFERENCES agreements(id) ON DELETE RESTRICT,
  qty NUMERIC(14,2) NOT NULL CHECK (qty >= 0),
  price NUMERIC(14,2) NOT NULL CHECK (price >= 0),
  sum_total NUMERIC(14,2) NOT NULL DEFAULT 0
);

-- Trigger to maintain sum_total
CREATE OR REPLACE FUNCTION set_sum_total() RETURNS trigger AS $$
BEGIN
  NEW.sum_total := COALESCE(NEW.qty,0) * COALESCE(NEW.price,0);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_sum_total ON stock_movements;
CREATE TRIGGER trg_set_sum_total
BEFORE INSERT OR UPDATE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION set_sum_total();
