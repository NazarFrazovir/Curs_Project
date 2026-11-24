-- 09_privacy.sql — Privacy Engineering (ЛР4): профіль, згоди, аудит, анонімізація.
-- Скрипт ідемпотентний: його можна запускати повторно на вже робочій базі.
SET search_path TO app, public;

-- ---------------------------------------------------------------------------
-- 0. Узгодження archive_history з кодом.
--    У 02_soft_delete.sql колонки названі actor_login/created_at, а inventory.py
--    пише в performed_by/performed_at. На чистій базі це ламало архівацію.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema='app' AND table_name='archive_history' AND column_name='actor_login')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema='app' AND table_name='archive_history' AND column_name='performed_by') THEN
    ALTER TABLE archive_history RENAME COLUMN actor_login TO performed_by;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema='app' AND table_name='archive_history' AND column_name='created_at')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema='app' AND table_name='archive_history' AND column_name='performed_at') THEN
    ALTER TABLE archive_history RENAME COLUMN created_at TO performed_at;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 1. Профіль користувача (прямі ідентифікатори та контактні дані) і статус акаунта
-- ---------------------------------------------------------------------------
ALTER TABLE keys ADD COLUMN IF NOT EXISTS full_name      TEXT;
ALTER TABLE keys ADD COLUMN IF NOT EXISTS email          TEXT;
ALTER TABLE keys ADD COLUMN IF NOT EXISTS phone          TEXT;
ALTER TABLE keys ADD COLUMN IF NOT EXISTS created_at     timestamptz NOT NULL DEFAULT now();
-- active — звичайний акаунт; anonymized — знеособлений (Art. 17); system — службовий запис
ALTER TABLE keys ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE keys ADD COLUMN IF NOT EXISTS anonymized_at  timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'keys_account_status_check') THEN
    ALTER TABLE keys ADD CONSTRAINT keys_account_status_check
      CHECK (account_status IN ('active', 'anonymized', 'system'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_keys_email ON keys (lower(email)) WHERE email IS NOT NULL;

-- Нейтральний системний запис: на нього посилаються бізнес-журнали після анонімізації
-- автора. Пароль — випадкове значення, яке ніхто не знає; вхід під ним неможливий.
INSERT INTO keys (login, password, role, account_status)
VALUES ('deleted-user', md5(random()::text || clock_timestamp()::text), 'Guest', 'system')
ON CONFLICT (login) DO NOTHING;
UPDATE keys SET account_status = 'system' WHERE login = 'deleted-user';

-- ---------------------------------------------------------------------------
-- 2. Налаштування (раніше створювались лише setup_db.py — на чистій базі вхід падав)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_prefs (
  user_login     TEXT PRIMARY KEY REFERENCES keys(login) ON DELETE CASCADE,
  theme          TEXT    DEFAULT 'dark',
  density        TEXT    DEFAULT 'normal',
  per_page       INTEGER DEFAULT 20,
  default_filter JSONB   DEFAULT '{}'::jsonb,
  updated_at     timestamptz DEFAULT now(),
  updated_by     TEXT
);
ALTER TABLE user_prefs ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
ALTER TABLE user_prefs ADD COLUMN IF NOT EXISTS updated_by TEXT;

-- ---------------------------------------------------------------------------
-- 3. Згоди (Art. 7): поточний стан за кожною метою + незмінна історія
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_consents (
  user_id        INT  NOT NULL REFERENCES keys(id),
  purpose        TEXT NOT NULL CHECK (purpose IN ('MARKETING_EMAIL', 'OPTIONAL_ANALYTICS')),
  is_granted     BOOLEAN NOT NULL,
  policy_version TEXT NOT NULL,
  granted_at     timestamptz,
  withdrawn_at   timestamptz,
  updated_at     timestamptz NOT NULL DEFAULT now(),
  source         TEXT NOT NULL,
  PRIMARY KEY (user_id, purpose)
);

CREATE TABLE IF NOT EXISTS consent_events (
  id             BIGSERIAL PRIMARY KEY,
  user_id        INT  NOT NULL REFERENCES keys(id),
  purpose        TEXT NOT NULL,
  action         TEXT NOT NULL CHECK (action IN ('GRANT', 'REVOKE')),
  policy_version TEXT NOT NULL,
  source         TEXT NOT NULL,
  correlation_id TEXT,
  occurred_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_consent_events_user ON consent_events (user_id, occurred_at);

-- Історія згод — доказ, тому лише дописується: зміна чи видалення заборонені.
CREATE OR REPLACE FUNCTION forbid_consent_event_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'consent_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_consent_events_append_only ON consent_events;
CREATE TRIGGER trg_consent_events_append_only
BEFORE UPDATE OR DELETE ON consent_events
FOR EACH ROW EXECUTE FUNCTION forbid_consent_event_change();

-- ---------------------------------------------------------------------------
-- 4. Залежні від згоди операції
-- ---------------------------------------------------------------------------
-- Черга маркетингових листів. Адреса отримувача тут НЕ копіюється (мінімізація):
-- вона береться з профілю в момент відправлення.
CREATE TABLE IF NOT EXISTS marketing_outbox (
  id            BIGSERIAL PRIMARY KEY,
  user_id       INT  NOT NULL REFERENCES keys(id),
  campaign      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'cancelled')),
  cancel_reason TEXT,
  created_at    timestamptz NOT NULL DEFAULT now(),
  processed_at  timestamptz
);
CREATE INDEX IF NOT EXISTS ix_marketing_outbox_status ON marketing_outbox (status);

-- Необов'язкова аналітика використання інтерфейсу
CREATE TABLE IF NOT EXISTS analytics_events (
  id          BIGSERIAL PRIMARY KEY,
  user_id     INT  NOT NULL REFERENCES keys(id),
  event_name  TEXT NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 5. Аудит privacy-операцій. Містить лише технічні ідентифікатори, результат
--    і лічильники — жодних значень персональних даних.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS privacy_audit (
  id             BIGSERIAL PRIMARY KEY,
  event_type     TEXT NOT NULL,
  actor_ref      TEXT NOT NULL,
  subject_ref    TEXT NOT NULL,
  result         TEXT NOT NULL,
  correlation_id TEXT,
  details        JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at    timestamptz NOT NULL DEFAULT now()
);
