#!/usr/bin/env bash
set -e
: "${SONAR_TOKEN:?Задай змінну SONAR_TOKEN}"
sonar-scanner \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token="$SONAR_TOKEN"