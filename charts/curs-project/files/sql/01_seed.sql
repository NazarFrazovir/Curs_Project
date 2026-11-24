-- 01_seed.sql
SET search_path TO app, public;

INSERT INTO keys(login,password,role) VALUES
  ('admin','admin','Admin'),
  ('operator','operator','Operator'),
  ('auth','auth','Authorized'),
  ('guest','guest','Guest')
ON CONFLICT (login) DO NOTHING;
