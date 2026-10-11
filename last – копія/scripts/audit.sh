#!/usr/bin/env bash
# SCA: перевірка залежностей на відомі вразливості (pip-audit, база PyPI/OSV).
# Код виходу 0 — вразливостей немає, 1 — знайдено.
set -e
cd "$(dirname "$0")/.."
pip-audit -r requirements.txt --progress-spinner off "$@"
