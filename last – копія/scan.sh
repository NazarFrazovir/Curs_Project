#!/usr/bin/env bash
set -e
: "${SONAR_TOKEN:?Задай змінну SONAR_TOKEN}"
ROOT="$(git rev-parse --show-toplevel)"
REL="${PWD#"$ROOT"/}"
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e SONAR_HOST_URL="http://host.docker.internal:9000" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0='*' \
  -v "$ROOT:/usr/src" \
  sonarsource/sonar-scanner-cli \
  -Dsonar.projectBaseDir="/usr/src/$REL" \
  -Dsonar.javascript.node.maxspace=1024