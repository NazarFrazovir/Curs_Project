#!/usr/bin/env bash
# Fault Injection для PostgreSQL через Toxiproxy (API на порту 8474).
#   ./fault.sh timeout  — БД перестає відповідати, з'єднання обривається через 500 мс
#   ./fault.sh reset    — прибрати всі збої (БД знову працює нормально)
#   ./fault.sh status   — показати активні збої
set -e
API="${TOXIPROXY_API:-http://localhost:8474}"
P="$API/proxies/postgres"
case "$1" in
  timeout)
    curl -sf -X POST "$P/toxics" -H 'Content-Type: application/json' \
      -d '{"name":"db_timeout","type":"timeout","stream":"downstream","attributes":{"timeout":500}}' ;;
  reset)
    curl -sf -X POST "$API/reset" && echo "all faults removed" ;;
  status)
    curl -sf "$P/toxics" ;;
  *)
    echo "usage: $0 {timeout|reset|status}"; exit 1 ;;
esac
echo
