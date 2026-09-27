SET search_path TO app, public;

ALTER TABLE keys ADD COLUMN IF NOT EXISTS last_login timestamptz;