# Curs_Project — Wholesale

Курсовий проєкт: вебсистема обліку оптового складу (Flask + PostgreSQL) і інженерний контур якості навколо неї: CI/CD, метрики, аудити ЛР1–ЛР10.

| Куди | Що там |
|---|---|
| [`last – копія/README.md`](last%20–%20копія/README.md) | **почніть звідси**: що робить система, швидкий старт, ролі, API, онбординг |
| [`docs/sdd.md`](docs/sdd.md) | як система влаштована: C4, компоненти, модель даних, контракти |
| [`docs/isd.md`](docs/isd.md) | де і як працює: середовища, змінні, CI/CD, бекапи, RTO/RPO |
| [`docs/architecture/adr/`](docs/architecture/adr/README.md) | чому прийнято ключові рішення |
| [`docs/audiences.md`](docs/audiences.md) | які питання закриває документація для кожної аудиторії |
| [`docs/maintenance.md`](docs/maintenance.md) | власники документів, цикли перегляду, правило «зміна коду = зміна документації» |
| [`docs/registry.json`](docs/registry.json) | реєстр усіх носіїв знань (аудит ЛР10) |

Код застосунку лежить у теці `last – копія/` (назва історична), CI — у `.github/workflows/`, git-хуки — у `githooks/`.
