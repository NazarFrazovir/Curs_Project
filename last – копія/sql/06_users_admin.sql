-- 06_users_admin.sql
SET search_path TO app, public;

-- Додаємо id, якщо його ще немає (для зв'язку з access_requests)
ALTER TABLE keys ADD COLUMN IF NOT EXISTS id serial;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'keys_id_uniq'
  ) THEN
    ALTER TABLE keys ADD CONSTRAINT keys_id_uniq UNIQUE (id);
  END IF;
END $$;

-- Унікальність login (login і так PRIMARY KEY, цей constraint зайвий,
-- але лишаємо ідемпотентним на випадок, якщо колись PK зміниться)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'keys_login_uniq'
  ) THEN
    ALTER TABLE keys ADD CONSTRAINT keys_login_uniq UNIQUE (login);
  END IF;
END $$;

-- Перевірка ролей (у 00_schema.sql вже є CHECK на role,
-- тож цей constraint, найімовірніше, зайвий і викличе помилку "already exists" —
-- тому огортаємо перевіркою)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'keys_role_check2'
  ) THEN
    -- пропускаємо: обмеження на role вже задане в 00_schema.sql
    NULL;
  END IF;
END $$;

-- Заявки доступу (від Гостя до Авторизованого)
CREATE TABLE IF NOT EXISTS access_requests (
  id            serial PRIMARY KEY,
  user_id       int NOT NULL REFERENCES keys(id) ON DELETE CASCADE,
  requested_role text NOT NULL DEFAULT 'Authorized'
    CHECK (requested_role IN ('Authorized')),
  message       text,
  status        text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','denied')),
  requested_at  timestamptz NOT NULL DEFAULT now(),
  processed_at  timestamptz,
  processed_by  text,
  admin_comment text
);

CREATE INDEX IF NOT EXISTS ix_access_requests_user ON access_requests(user_id);
CREATE INDEX IF NOT EXISTS ix_access_requests_status ON access_requests(status);