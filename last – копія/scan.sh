#!/usr/bin/env bash
# DEPRECATED (ADR-0004): локальний SonarQube; актуальний аналіз — SonarCloud і job quality-metrics у CI.
set -e
: "${SONAR_TOKEN:?Задай змінну SONAR_TOKEN}"
sonar-scanner \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token="$SONAR_TOKEN"