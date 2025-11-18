-- 05_overheads.sql
SET search_path TO app, public;

CREATE TABLE IF NOT EXISTS overheads (
  id        serial PRIMARY KEY,
  dt        date NOT NULL,
  category  text NOT NULL,
  amount    numeric(12,2) NOT NULL CHECK (amount >= 0),
  note      text
);

CREATE INDEX IF NOT EXISTS ix_overheads_dt ON overheads(dt);

-- приклад даних
INSERT INTO overheads(dt, category, amount, note) VALUES
  (CURRENT_DATE - 14, 'Оренда', 15000, 'склад'),
  (CURRENT_DATE - 10, 'Комунальні', 3200,  'жовтень'),
  (CURRENT_DATE - 5,  'ЗП', 42000,         'оператори')
ON CONFLICT DO NOTHING;
