#!/usr/bin/env bash
# Встановлення хуків проєкту: копія в .git/hooks/ (класичний спосіб, як у методичці ЛР6).
# Якщо в репозиторії налаштовано core.hooksPath, Git читає хуки звідти, а .git/hooks ігнорує.
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ -n "$(git config --get core.hooksPath || true)" ]]; then
  echo "core.hooksPath = $(git config --get core.hooksPath) — вимикаю, щоб працював .git/hooks/"
  git config --unset core.hooksPath
fi

HOOKS_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS_DIR"
for hook in pre-commit pre-commit-complexity post-commit; do
  cp "githooks/$hook" "$HOOKS_DIR/$hook"
  chmod +x "$HOOKS_DIR/$hook"
  echo "✔ $HOOKS_DIR/$hook"
done
