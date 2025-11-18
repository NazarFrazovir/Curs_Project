-- 06_users_admin.sql
SET search_path TO app, public;

-- Keys: унікальний логін + контроль ролей
ALTER TABLE keys
  ADD CONSTRAINT keys_login_uniq UNIQUE (login);

ALTER TABLE keys
  ADD CONSTRAINT keys_role_check CHECK (role IN ('Admin','Operator','Authorized','Guest'));

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
