# Wholesale — облік оптового складу (Flask + PostgreSQL)

**Що це і для кого.** Вебсистема для працівників оптового складу. Вона веде довідники постачальників, клієнтів, товарів і договорів, журнал надходжень (`IN`) і відвантажень (`OUT`), показує залишки, формує CSV-накладні та аналітичні звіти (топ клієнтів, рентабельність, порогові вибірки). Персональні дані користувачів захищені за GDPR: маскування в логах, експорт, анонімізація, згоди.

Архітектурний паспорт: [SDD](../docs/sdd.md) (як влаштовано) · [ISD](../docs/isd.md) (де і як розгорнуто) · [ADR](../docs/architecture/adr/README.md) (чому так) · [регламент документації](../docs/maintenance.md).

## Швидкий старт (Docker, рекомендовано)

```bash
cd "last – копія"
cp .env.example .env              # задайте POSTGRES_PASSWORD і SECRET_KEY
docker compose up -d --build      # db → toxiproxy → web
open http://localhost:5050        # Linux: xdg-open
```

Порядок запуску: `db` (чекаємо healthy) → `toxiproxy` → `web`. При **першому** старті БД автоматично виконує всі міграції `sql/00…09`. Деталі, порти, змінні — в [ISD](../docs/isd.md).

Сід `sql/01_seed.sql` створює демо-обліковий запис **`admin` / `admin`**. Змініть пароль одразу після першого входу (`/profile`). Нові користувачі подають заявку на доступ через `/request-access`.

## Запуск без Docker (розробка)

1. PostgreSQL 16 і БД `wholesale_db`.
2. Виконайте **усі** міграції по порядку: `for f in sql/*.sql; do psql -d wholesale_db -f "$f"; done` (`00_schema` … `09_privacy`, номера `08` немає).
3. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`
4. У `.env` задайте `DATABASE_URL=postgresql://USER:PASS@localhost:5432/wholesale_db` і `SECRET_KEY`.
5. `FLASK_DEBUG=1 python app.py` → http://localhost:5000

## Тести і перевірки якості

```bash
pytest -q                                      # юніт-тести; інтеграційні privacy — з TEST_DATABASE_URL
ruff check .
lizard -l python -C 10 -w .                    # жодна функція не має CC > 10
python scripts/doc_audit.py --gate             # актуальність документації (ЛР10)
bash ../githooks/install.sh                    # pre-commit: складність + gitleaks
```

CI (GitHub Actions) запускає все це на кожен push і PR у `main` (див. [ISD §5](../docs/isd.md#5-cicd-конвеєр)).

## Ролі

| Роль | Можливості |
|---|---|
| Admin | усе, плюс користувачі, заявки на доступ, відновлення з архіву, `uncancel` руху |
| Operator | додавання, редагування, архівування довідників, рухи, скасування руху, SQL-консоль |
| Authorized | перегляд, пошук, звіти |
| Guest | перегляд |

## Публічний JSON API

| Метод | Маршрут | Що повертає |
|---|---|---|
| GET | `/api/balance` | залишки товарів; при недоступній БД віддає кеш (`degraded: true`) або 503 |
| GET | `/api/me` | профіль поточного користувача |
| GET | `/api/users/<int:user_id>/personal-data` | експорт персональних даних суб'єкта (GDPR, ст. 15/20) |
| POST | `/api/users/<int:user_id>/anonymize` | анонімізація облікового запису (ст. 17) |
| GET | `/api/privacy/erasure-policy` | політика видалення даних |
| GET | `/api/users/<int:user_id>/consents` | стан згод користувача |
| POST | `/api/users/<int:user_id>/consents/<purpose>/grant` | надати згоду (`MARKETING_EMAIL`, `OPTIONAL_ANALYTICS`) |
| POST | `/api/users/<int:user_id>/consents/<purpose>/revoke` | відкликати згоду |
| POST | `/api/users/<int:user_id>/marketing-email` | поставити лист у чергу (лише за згодою) |
| POST | `/api/users/<int:user_id>/analytics-events` | записати подію аналітики (лише за згодою) |
| POST | `/api/marketing/dispatch` | обробити чергу розсилки |

Повний перелік HTTP-маршрутів (HTML і JSON) наведено в [SDD §5.2](../docs/sdd.md#52-http-контракти-повний-перелік-маршрутів).

## Онбординг нового розробника

1. Прочитайте цей README і [SDD §1–3](../docs/sdd.md): що робить система, з яких компонентів складається.
2. Підніміть систему через Docker (вище) і увійдіть під адміністратором.
3. Встановіть хуки: `bash ../githooks/install.sh`. Запустіть `pytest -q` і `ruff check .`.
4. Перед першим PR прочитайте [maintenance.md](../docs/maintenance.md). Головне правило: **зміна коду = зміна документації**.
