# ADR-0003: Статичний аналіз локальним SonarQube у Docker

- **Статус:** Superseded by [ADR-0004](0004-sonarcloud-instead-of-local-sonarqube.md) (2026-11-02)
- **Дата рішення:** 2026-10-04 (ЛР1, коміт «Baseline scan»)
- **Власник:** NazarFrazovir (El)

## Контекст
Для ЛР1 потрібен був аналіз якості (баги, вразливості, дублювання) і технічний борг SQALE. Хмарних інтеграцій у проєкті ще не було.

## Розглянуті альтернативи
* SonarQube Community у Docker (`docker-compose.sonar.yml`) + `sonar-scanner` (`scan.sh`, post-commit хук);
* SonarCloud — потребував налаштування GitHub-інтеграції;
* лише ruff/flake8 — без SQALE-моделі боргу.

## Рішення
Підняти локальний SonarQube на `localhost:9000`, сканувати `scan.sh` з `SONAR_TOKEN`, проєкт `curs-project`.

## Наслідки
* ✅ Швидкий старт без облікових записів.
* ⚠️ Результати живуть лише на одному ноутбуці. Сервер треба піднімати вручну, а post-commit хук падає, коли він вимкнений.
