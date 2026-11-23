# Documentation Currency Audit — 2026-11-23

| Документ | Тип | Оновлено | Вік, дн. | Комітів doc | Комітів коду | Код після doc | Посилань | Сигнали |
|---|---|---|---:|---:|---:|---:|---:|---|
| `last – копія/README.md` | product | 2026-11-23 | 0 | 2 | 43 | 1 | 7 | відстає від коду на 1 коміт(и) |
| `last – копія/PRIVACY.md` | product | 2026-11-23 | 0 | 2 | 4 | 0 | 4 | OK |
| `last – копія/LR5_report.md` | process | 2026-11-02 | 21 | 1 | 4 | 2 | 3 | OK |
| `last – копія/experiments/lab5/README.md` | process | 2026-11-01 | 22 | 1 | 2 | 1 | 3 | OK |
| `last – копія/experiments/lab6/README.md` | process | 2026-11-23 | 0 | 2 | 10 | 0 | 3 | OK |
| `last – копія/experiments/lab9/LR9_report.md` | process | 2026-11-22 | 1 | 1 | 1 | 0 | 4 | OK |
| `last – копія/FINANCIAL_LEDGER.md` | process | 2026-11-22 | 1 | 1 | 1 | 0 | 7 | OK |
| `last – копія/.env.example` | product | 2026-11-23 | 0 | 3 | 11 | 1 | 6 | відстає від коду на 1 коміт(и) |
| `last – копія/docker-compose.yml` | product | 2026-11-23 | 0 | 4 | 3 | 0 | 4 | OK |
| `last – копія/docker-compose.sonar.yml` | product | 2026-11-23 | 0 | 3 | 4 | 0 | 4 | OK |
| `.github/workflows/ci.yml` | product | 2026-11-08 | 15 | 5 | 10 | 5 | 5 | відстає від коду на 5 коміт(и) |
| `githooks/install.sh` | product | 2026-11-08 | 15 | 1 | 3 | 0 | 4 | OK |
| `last – копія/sql/00_schema.sql` | product | 2025-11-18 | 370 | 1 | 4 | 3 | 3 | ймовірно застарілий (>180 дн.); прострочено перегляд (180 дн.); відстає від коду на 3 коміт(и) |
| `last – копія/sonar-project.properties` | product | 2026-11-23 | 0 | 3 | 2 | 0 | 3 | OK |
| `app.py` | product | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `docstrings і коментарі в *.py` | product | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `git log (56+ повідомлень комітів)` | process | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `GitHub Pull Requests #1–#4` | process | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `звіти ЛР6–ЛР8 і пояснення (поза репозиторієм)` | process | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `docs/sdd.md` | product | 2026-11-23 | 0 | 1 | 27 | 1 | 8 | відстає від коду на 1 коміт(и) |
| `docs/isd.md` | product | 2026-11-23 | 0 | 1 | 14 | 1 | 7 | відстає від коду на 1 коміт(и) |
| `last – копія/setup_db.py` | product | — |  | 0 | 0 | 0 | 0 | не файл / немає в репозиторії |
| `docs/architecture/adr/0001-postgresql-raw-sql.md` | product | 2026-11-23 | 0 | 1 | 0 | 0 | 2 | OK |
| `docs/architecture/adr/0002-flask-modular-monolith.md` | product | 2026-11-23 | 0 | 1 | 0 | 0 | 2 | OK |
| `docs/audiences.md` | product | 2026-11-23 | 0 | 1 | 0 | 0 | 4 | OK |
| `docs/maintenance.md` | product | 2026-11-23 | 0 | 1 | 0 | 0 | 4 | OK |

## Структурний дрейф паспорта

- SDD: маршрути без опису: **2**: `/api/health`, `/api/stock-alerts`
- SDD: таблиці без опису: OK
- README: публічні /api маршрути без опису: **2**: `/api/health`, `/api/stock-alerts`
- ISD: сервіси compose без опису: OK
- ISD: змінні оточення без опису: **1**: `STOCK_ALERT_THRESHOLD`

## Вердикт: **FAIL — Documentation Decay**

- last – копія/README.md: відстає від коду на 1 коміт(и)
- last – копія/.env.example: відстає від коду на 1 коміт(и)
- docs/sdd.md: відстає від коду на 1 коміт(и)
- docs/isd.md: відстає від коду на 1 коміт(и)
- SDD: маршрути без опису: 2
- README: публічні /api маршрути без опису: 2
- ISD: змінні оточення без опису: 1
