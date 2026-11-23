# ADR-0004: SonarCloud + метрики якості в CI замість локального SonarQube

- **Статус:** Accepted
- **Дата рішення:** 2026-11-02 (ЛР5, коміт «fix(lab5): CI container job path, SonarCloud findings»)
- **Замінює:** [ADR-0003](0003-local-sonarqube.md)
- **Власник:** NazarFrazovir (El)

## Контекст
Локальний SonarQube (ADR-0003) не відтворюваний: метрики залежать від того, чи піднятий сервер на ноутбуці. Для ЛР5 потрібні ізольовані відтворювані вимірювання й Quality Gates, що блокують злиття.

## Розглянуті альтернативи
* залишити локальний SonarQube і запускати його в CI як service-контейнер — важкий (≥ 2 ГБ RAM), довгий старт;
* SonarCloud (безкоштовний для публічних репозиторіїв) + власні метрики в CI (`collect_metrics.py`, `balanced_gate.py`, pinned lock-файл);
* лише власні метрики без SQALE.

## Рішення
SonarCloud (ключ проєкту `NazarFrazovir_Curs_Project`) — для SQALE і issues. Блокуючі ворота (CCN, Cognitive, Coverage AND Mutation) рахуються в job `quality-metrics` у контейнері з фіксованими версіями інструментів ([ISD §5](../../isd.md#5-cicd-конвеєр)).

## Наслідки
* ✅ Метрики відтворювані й видні всім у PR.
* ⚠️ `docker-compose.sonar.yml`, `scan.sh` і post-commit хук стали **deprecated**. Вони позначені так у файлах і в [реєстрі документації](../../registry.json).
