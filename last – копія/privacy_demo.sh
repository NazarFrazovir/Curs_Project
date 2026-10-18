#!/usr/bin/env bash
# Сценарії захисту ЛР4 (Privacy Engineering). Запускати з папки проєкту, коли
# піднято docker compose і активовано .venv.
#
#   bash privacy_demo.sh 1      Secure Logging
#   bash privacy_demo.sh 2      Personal Data Export
#   bash privacy_demo.sh 3      Erasure / Anonymization
#   bash privacy_demo.sh 4      Consent Policy Enforcement
#   bash privacy_demo.sh tests  усі тести ЛР4
#   bash privacy_demo.sh seed   відновити демо-користувачів
#
# Усі дані синтетичні (example.com, неіснуючий код оператора 00).
set -u

BASE="${BASE:-http://localhost:5050}"
JARS="${TMPDIR:-/tmp}/lab4-cookies"
PY="${PYTHON:-python3}"
mkdir -p "$JARS"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${POSTGRES_USER:?POSTGRES_USER не задано (.env)}"
: "${POSTGRES_DB:?POSTGRES_DB не задано (.env)}"
TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD:-}@localhost:5433/wholesale_test}"
export TEST_DATABASE_URL

title() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$1"; }
pause() { printf '\n\033[1m%s\033[0m  [Enter] ' "$1"; read -r _; }

pretty() {
  "$PY" -c '
import json, sys
raw = sys.stdin.read()
body, _, status = raw.rpartition("\n<- HTTP ")
try:
    print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
except ValueError:
    print(body)
print("<- HTTP " + status.strip())'
}

login() {  # login <jar> <login> <password>
  rm -f "$JARS/$1.jar"
  curl -s -o /dev/null -c "$JARS/$1.jar" -X POST \
       --data-urlencode "login=$2" --data-urlencode "password=$3" "$BASE/login"
}

api() {    # api <jar|anon> <METHOD> <path> [json]
  local jar="$JARS/$1.jar"
  [ "$1" = anon ] && jar=/dev/null
  if [ $# -ge 4 ]; then
    curl -s -b "$jar" -c "$jar" -X "$2" -H "Content-Type: application/json" -d "$4" \
         -w '\n<- HTTP %{http_code}\n' "$BASE$3" | pretty
  else
    curl -s -b "$jar" -c "$jar" -X "$2" -w '\n<- HTTP %{http_code}\n' "$BASE$3" | pretty
  fi
}

uid() { curl -s -b "$JARS/$1.jar" "$BASE/api/me" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }

db() { docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q \
         -c "SET search_path TO app, public" -c "$1"; }

seed() { docker compose exec -T web python -m privacy.demo_seed; }

ensure_test_db() {
  docker compose exec -T db createdb -U "$POSTGRES_USER" wholesale_test 2>/dev/null || true
}

step1() {
  seed >/dev/null
  title "Крок 1. Secure Logging — операція з email, телефоном, паролем і токенами"
  docker compose exec -T web python -m privacy.log_demo
  pause "Той самий запис у форматі JSON"
  docker compose exec -T web python -m privacy.log_demo --json
  pause "Реальні запити до застосунку і їхній журнал"
  login olena olena.demo demo-pass-1
  curl -s -o /dev/null -b "$JARS/olena.jar" "$BASE/admin/users?q=olena.demo@example.com&page=2"
  curl -s -o /dev/null -b "$JARS/olena.jar" "$BASE/api/users/$(uid olena)/personal-data"
  docker compose logs web --since 20s --no-log-prefix | tail -n 8
  pause "Автоматизований тест: відкритих значень у журналі немає"
  "$PY" -m pytest tests/gdpr/test_privacy_logging.py -v
}

step2() {
  seed >/dev/null
  login olena olena.demo demo-pass-1
  login petro petro.demo demo-pass-2
  OLENA=$(uid olena)
  title "Крок 2. Експорт власних даних: olena.demo -> /api/users/$OLENA/personal-data"
  api olena GET "/api/users/$OLENA/personal-data"
  pause "Негативний сценарій: petro.demo запитує дані olena.demo"
  api petro GET "/api/users/$OLENA/personal-data"
  title "...і неіснуючий id — відповідь ідентична, факт існування не розкрито"
  api petro GET "/api/users/999999/personal-data"
  title "Без входу"
  api anon GET "/api/users/$OLENA/personal-data"
  title "Журнал: лише факт, actor/subject id, результат, correlation ID"
  docker compose logs web --since 30s --no-log-prefix | grep "privacy.export" | tail -n 4
}

show_subject_state() {
  db "SELECT id, login, full_name, email, phone, account_status FROM keys WHERE id = $1"
  db "SELECT user_login, theme, density FROM user_prefs WHERE user_login = '$2'"
  db "SELECT id, status, message, admin_comment, processed_by FROM access_requests WHERE user_id = $1"
  db "SELECT id, entity_type, action, performed_by FROM archive_history
       WHERE performed_by IN ('$2', '$3') ORDER BY id DESC LIMIT 4"
  db "SELECT purpose, is_granted, source, withdrawn_at IS NOT NULL AS withdrawn FROM user_consents WHERE user_id = $1"
}

step3() {
  seed >/dev/null
  login olena olena.demo demo-pass-1
  login admin admin admin
  OLENA=$(uid olena)
  api olena POST "/api/users/$OLENA/consents/MARKETING_EMAIL/grant" '{"policy_version":"2026-10-01"}' >/dev/null
  title "Крок 3. Стан БД ДО анонімізації (subject id=$OLENA)"
  show_subject_state "$OLENA" olena.demo deleted-user
  pause "Запит на анонімізацію від самої olena.demo"
  api olena POST "/api/users/$OLENA/anonymize" '{"confirm": true}'
  pause "Стан БД ПІСЛЯ"
  show_subject_state "$OLENA" olena.demo deleted-user
  pause "Пошук слідів PII у всіх текстових колонках схеми app"
  docker compose exec -T web python -m privacy.pii_scan "olena.demo" "111 22 33" "Олена Тестова"
  pause "Повторний запит (ідемпотентність) і спроба зі старою сесією"
  api olena POST "/api/users/$OLENA/anonymize" '{"confirm": true}'
  api admin POST "/api/users/$OLENA/anonymize" '{"confirm": true}'
  title "Audit event без PII"
  db "SELECT event_type, actor_ref, subject_ref, result, correlation_id, details
        FROM privacy_audit WHERE event_type = 'ERASURE' ORDER BY id DESC LIMIT 2"
}

step4() {
  seed >/dev/null
  login petro petro.demo demo-pass-2
  PETRO=$(uid petro)
  title "Крок 4. Початковий стан згод petro.demo"
  api petro GET "/api/users/$PETRO/consents"
  title "Залежна дія без згоди -> DENY"
  api petro POST "/api/users/$PETRO/marketing-email" '{"campaign":"autumn-sale"}'
  pause "GRANT для мети MARKETING_EMAIL"
  api petro POST "/api/users/$PETRO/consents/MARKETING_EMAIL/grant" '{"policy_version":"2026-10-01","source":"web_settings"}'
  title "Та сама дія -> ALLOW, лист у черзі"
  api petro POST "/api/users/$PETRO/marketing-email" '{"campaign":"autumn-sale"}'
  title "Згода на маркетинг НЕ дає дозволу на аналітику"
  api petro POST "/api/users/$PETRO/analytics-events" '{"event":"page.view"}'
  pause "REVOKE тієї самої згоди"
  api petro POST "/api/users/$PETRO/consents/MARKETING_EMAIL/revoke" '{"source":"web_settings"}'
  title "Повтор дії -> DENY, побічного ефекту немає"
  api petro POST "/api/users/$PETRO/marketing-email" '{"campaign":"autumn-sale"}'
  db "SELECT id, campaign, status, cancel_reason FROM marketing_outbox WHERE user_id = $PETRO ORDER BY id"
  db "SELECT purpose, action, policy_version, source, occurred_at FROM consent_events
       WHERE user_id = $PETRO ORDER BY id DESC LIMIT 4"
  pause "Інтеграційний тест GRANT -> ALLOW -> REVOKE -> DENY"
  ensure_test_db
  "$PY" -m pytest "tests/gdpr/test_privacy_consent.py::test_grant_allow_revoke_deny_scenario" \
                  "tests/gdpr/test_privacy_consent.py::test_consent_for_one_purpose_does_not_allow_another" -v
}

case "${1:-}" in
  1) step1 ;;
  2) step2 ;;
  3) step3 ;;
  4) step4 ;;
  seed) seed ;;
  tests) ensure_test_db; "$PY" -m pytest tests/gdpr -v ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
