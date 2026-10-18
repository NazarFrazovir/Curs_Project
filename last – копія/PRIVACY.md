# Privacy Engineering (ЛР4): технічна документація

Код: пакет `privacy/`, міграція `sql/09_privacy.sql`, тести `tests/gdpr/`, демо `privacy_demo.sh`.
Підключення в `app.py`: `configure_logging()` замість `logging.basicConfig(...)` та `init_privacy(app)` у `create_app()`.

Цикл: інвентаризація PII → безпечне логування → автоматизована перевірка → авторизований експорт →
перевірка повноти й мінімізації → анонімізація → контроль цілісності → Consent Policy Gate → тести.

---

## 1. Інвентаризація персональних даних

| Категорія | Поля | Сховище | Пов'язані сутності | У логах | В експорті | При видаленні |
|---|---|---|---|---|---|---|
| Прямі ідентифікатори | `login`, `full_name` | `keys` | `user_prefs.user_login` (FK), `archive_history.performed_by` (FK) | маска `О***` | так | login → випадковий `anon-*`, ПІБ → NULL |
| Контактні дані | `email`, `phone` | `keys`; копії у вільному тексті `access_requests.message/admin_comment` | — | маска `o***@example.com`, `+**********33` | так | NULL; вільний текст → NULL |
| Облікові дані (секрет) | `password` | `keys` | — | `[REDACTED]` | **ніколи** | випадкове непридатне значення |
| Технічні ідентифікатори | `keys.id`, IP клієнта, session cookie, correlation ID | `keys`, журнали веб-сервера | усі FK на `keys.id` | id — так (`user:7`); IP — `127.0.x.x`; cookie — `[REDACTED]` | `subject_id` | id лишається як знеособлений якір |
| Налаштування | `theme`, `density`, `per_page`, `default_filter` | `user_prefs` | `keys.login` | ні | так | DELETE |
| Історія дій | автор дії, дата, сутність, причина | `archive_history`, `*.archived_by`, `stock_movements.canceled_by` | `keys.login` | ні | так (`archive_history`) | автор → `deleted-user` |
| Заявки на доступ | роль, статус, повідомлення, коментар адміна | `access_requests` | `keys.id`; `processed_by` — **інший** користувач | ні | так, без `processed_by` | RETAIN, текст → NULL |
| Дані про згоду | мета, версія політики, час, канал | `user_consents`, `consent_events` | `keys.id` | лише мета й результат | так | відкликати, історію зберегти |
| Комунікації та аналітика | кампанія, статус; назва події | `marketing_outbox`, `analytics_events` | `keys.id` | лише id запису | так | DELETE |
| Транзакційні записи | рухи товарів, договори | `stock_movements`, `agreements`, `customers`, `suppliers` | контрагенти | — | ні (дані інших осіб) | SKIP, крім полів-авторів |

**Ніколи не повертаються через експорт:** `keys.password`, `keys.account_status`, таблиця `privacy_audit`,
`access_requests.processed_by` (дані іншого користувача), `consent_events.correlation_id`.

**Контрольні тестові дані** (синтетичні): `olena.demo` / `olena.demo@example.com` / `+380 00 111 22 33` /
«Олена Тестова»; `petro.demo` — «інший користувач». Домен `example.com` зарезервований (RFC 2606),
код оператора `00` не існує. В інтеграційних тестах користувачі генеруються з унікальним суфіксом.

---

## 2. Secure Logging (Завдання 1)

**Політика полів** (`privacy/sanitizer.py`):

| Дія | Поля / шаблони |
|---|---|
| FORBIDDEN → `[REDACTED]` | `password`, `*token*`, `api_key`, `secret`, `session`, `cookie`, `authorization`, `credential`, `security_answer`, `address`; у тексті: `key=value`, `"key": "value"`, `Bearer …`, JWT, пароль у URL (`postgresql://u:***@h`), зареєстровані значення `SECRET_KEY`/пароля БД |
| MASKED (частково) | email → `o***@example.com`; телефон → `+**********33`; IPv4 → `192.168.x.x`; `full_name`/`name`/`login` → `О***`; значення query-параметрів, крім `page`, `per_page`, `sort`… |
| ALLOWED | `correlation_id`, тип операції, результат, `actor`/`subject` як `user:<id>`, лічильники, коди помилок, тип exception і traceback |

**Механізм.** Точка інтеграції — фабрика `LogRecord` (`logging.setLogRecordFactory`): через неї проходить
кожен запис процесу, з будь-якого модуля, Flask, werkzeug, gunicorn. Обробляються повідомлення, аргументи
(включно з вкладеними dict/list/dataclass/DTO), текст exception і ланцюжок причин, stack. `PiiFilter` на
handler'ах додатково обробляє `extra`-поля та записи, створені в обхід фабрики (`logging.makeLogRecord`).
Форматери: текстовий і JSON (`LOG_FORMAT=json`); JSON очищується на рівні структури, тож лишається валідним.
Correlation ID приходить із заголовка `X-Request-ID` або генерується й повертається у відповіді.

**Не логувати зайве.** Події безпеки пишуться через `security_event()`: факт, `actor=user:<id>`,
`subject=user:<id>`, результат, correlation ID. Експорт логує лише лічильники секцій, а не JSON.

**До / після** (синтетичні дані):
```
python -m privacy.log_demo --unsafe   # ДО: стандартний logging
python -m privacy.log_demo            # ПІСЛЯ: текст
python -m privacy.log_demo --json     # ПІСЛЯ: JSON
```

**Обмеження.** Ім'я у вільному тексті («Олена Тестова» всередині речення) шаблоном не розпізнати;
ім'я маскується лише як поле структури. Тому правило коду: ПІБ у текст повідомлення не підставляється.
Пароль без мітки (`"%s"` замість `"password=%s"`) теж не розпізнати за значенням; рятує лише структура
(`extra={"password": …}`) або реєстрація відомого значення (`register_secret`).

**Тести:** `tests/gdpr/test_privacy_logging.py` — текст, JSON, усі логери процесу, вкладені DTO,
exception із причиною, обхід фабрики, і контрольний тест, що детектор падає без захисту.

---

## 3. Personal Data Export (Завдання 2)

| Метод | Шлях | Хто | Відповіді |
|---|---|---|---|
| GET | `/api/me` | будь-хто з сесією | 200 `{id, role}` / 401 |
| GET | `/api/users/{id}/personal-data` | сам суб'єкт або роль з `privacy.export.any` (Admin) | 200 / 401 / 404 |

Принципал — користувач сесії, але `id` і роль читаються **з БД** (підміна ролі в cookie нічого не дає).
Чужий і неіснуючий `id` дають однакову відповідь `404 {"error":"not_found"}`.

**Контракт** (`schema_version` 1.0, час — ISO 8601 UTC із `Z`, кожна секція присутня завжди):

| Секція | Джерело |
|---|---|
| `meta` | версія схеми, час формування, `subject_id`, `request_id`, `sources`, `excluded` |
| `profile` | `keys` |
| `settings` | `user_prefs` (або `null`) |
| `access_requests` | `access_requests` без `processed_by` |
| `activity.archive_history` | `archive_history` за `performed_by` |
| `consents.current` / `.history` | `user_consents` / `consent_events` |
| `communications.marketing_emails` | `marketing_outbox` |
| `analytics.events` | `analytics_events` |

Відповідь має `Cache-Control: no-store`. Кожен експорт фіксується в `privacy_audit` (лише лічильники).

**Тести:** `tests/gdpr/test_privacy_export.py` — повнота (контрольне значення з кожного джерела),
мінімізація (рекурсивна перевірка заборонених ключів і відсутність пароля в сирому тілі), однакова
відмова для чужого й неіснуючого id, 401, підміна ролі, Admin, стабільна схема без даних, відсутність PII в логах.

---

## 4. Erasure / Anonymization (Завдання 3)

`POST /api/users/{id}/anonymize`, тіло `{"confirm": true}` (лише JSON, тому звичайна HTML-форма з
чужого сайту такий запит не надішле). Доступ: сам суб'єкт або `privacy.erase.any` (Admin).
Політика доступна також через `GET /api/privacy/erasure-policy`.

| Джерело | Дія | Обґрунтування |
|---|---|---|
| `keys` | ANONYMIZE | якір для FK історії згод і заявок; login → випадковий `anon-<hex>`, пароль → випадкове значення, ПІБ/email/телефон/last_login → NULL, роль → Guest |
| `user_prefs` | DELETE | налаштування без підстав для зберігання |
| `access_requests` | RETAIN + ANONYMIZE | історія надання прав (accountability); вільний текст → NULL |
| `archive_history`, `*.archived_by`, `stock_movements.canceled_by`, `access_requests.processed_by`, `user_prefs.updated_by` | RETAIN + ANONYMIZE | облік складу зберігається (модельне правило); автор → системний запис `deleted-user` |
| `user_consents` | RETAIN + WITHDRAW | усі згоди відкликаються (`source=erasure`) |
| `consent_events` | RETAIN | доказ згоди (Art. 7(1)); PII не містить |
| `marketing_outbox`, `analytics_events` | DELETE | необов'язкові дані |
| `privacy_audit` | RETAIN | PII не містить за побудовою |
| журнали застосунку | SKIP | PII туди не потрапляють (Завдання 1) |
| контрагенти, рухи товарів (дані) | SKIP | дані інших осіб |

Колонки з FK на `keys(login)` знаходяться автоматично через `pg_constraint`, тож нове посилання,
додане пізніше, не буде пропущене.

**Чому це анонімізація, а не псевдонімізація.** Новий логін генерується `secrets`, а не обчислюється з
початкового (хеш логіна можна перерахувати для відомого логіна → повторна ідентифікація). Таблиці
відповідності не існує. Автор у бізнес-журналах — спільний `deleted-user` для всіх видалених, тож записи
одного видаленого користувача не зв'язуються між собою.

**Транзакція та ідемпотентність.** Усі кроки (`ERASURE_STEPS`) виконуються в одній транзакції з
`SELECT … FOR UPDATE`. Збій на будь-якому кроці → повний rollback, а факт збою пишеться в аудит окремою
транзакцією. Повторний запит → `already_anonymized` без змін. Стара сесія видаленого користувача
очищається на наступному запиті (перевірка статусу акаунта в `before_request`).

**Тести:** `tests/gdpr/test_privacy_erasure.py` — пошук кожного PII-значення в усіх текстових/JSON
колонках схеми, збереження бізнес-записів і відсутність «сиріт», робота звітних сторінок, повторний
запуск, rollback при збої посередині, заборона для іншого actor, аудит без PII, втрата сесії і входу.

---

## 5. Consent Management (Завдання 4)

**Модель.** `user_consents` (поточний стан: `user_id`, `purpose`, `is_granted`, `policy_version`,
`granted_at`, `withdrawn_at`, `updated_at`, `source`) і `consent_events` (append-only історія GRANT/REVOKE
з версією, каналом, часом і correlation ID; тригер забороняє UPDATE і DELETE).
Мети: `MARKETING_EMAIL`, `OPTIONAL_ANALYTICS`, кожна зі своєю чинною версією політики (`privacy/consent.py`).

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/api/users/{id}/consents` | стан за кожною метою + фактичне рішення Gate + історія |
| POST | `/api/users/{id}/consents/{purpose}/grant` | `{"policy_version": "2026-10-01", "source": "web_settings"}` |
| POST | `/api/users/{id}/consents/{purpose}/revoke` | `{"source": "web_settings"}` |
| POST | `/api/users/{id}/marketing-email` | залежна дія: лист у чергу (202 ALLOW / 403 DENY) |
| POST | `/api/users/{id}/analytics-events` | залежна дія: подія аналітики |
| POST | `/api/marketing/dispatch` | фонова задача відправлення черги (Admin/Operator) |

GRANT і REVOKE дає лише сам суб'єкт; повтор не створює нової події. Версія політики має збігатися з
чинною (інакше 409 з актуальною версією). Канали API: `web_settings`, `api`, `mobile_app`.

**Policy Gate** (`ConsentPolicyGate.check`) викликається безпосередньо перед побічним ефектом і читає
стан із БД щоразу (кешу немає). DENY, якщо згоди немає, її відкликано або версія застаріла.
`FOR SHARE` на рядку згоди не дає конкурентному REVOKE проскочити між перевіркою й дією.
Після REVOKE поставлені в чергу листи скасовуються, а фонова задача перевіряє згоду ще раз перед кожним
листом. Gate стоїть лише перед optional-операціями: вхід, експорт, видалення, склад від згоди не залежать.

**Тести:** `tests/gdpr/test_privacy_consent.py` — DENY → GRANT → ALLOW → REVOKE → DENY без побічного
ефекту, ізоляція мет, ідемпотентність, нова версія політики, повторна перевірка у фоновій задачі, права
на dispatch, consent не є універсальним прапорцем, авторизація й валідація, append-only історія.

---

## 6. Маскування, псевдонімізація, анонімізація, видалення

| Механізм | Що це | Де в проєкті |
|---|---|---|
| Маскування | частина значення прихована для конкретного виводу, оригінал у БД не змінюється | журнали: `o***@example.com` |
| Псевдонімізація | ідентифікатор замінено, але зв'язок можна відновити з додатковою інформацією; це все ще персональні дані | `user:7` у журналах і аудиті: за таблицею `keys` відомо, хто це, поки акаунт активний |
| Анонімізація | зв'язок з особою незворотно розірвано, відновити неможливо навіть власнику системи | акаунт після `/anonymize`: випадковий логін, NULL у PII, `deleted-user` у журналах |
| Видалення | запис фізично знищено | `user_prefs`, `marketing_outbox`, `analytics_events` |

---

## 7. Запуск

```bash
# міграція на робочій базі (на новому томі виконується автоматично)
docker compose exec -T db psql -U postgres -d wholesale_db -v ON_ERROR_STOP=1 < sql/09_privacy.sql
docker compose up -d --build web
docker compose exec web python -m privacy.demo_seed

# тести (окрема тестова БД — її схема перестворюється)
docker compose exec db createdb -U postgres wholesale_test
TEST_DATABASE_URL=postgresql://postgres:<пароль>@localhost:5433/wholesale_test pytest tests/gdpr -v

# демонстрація
bash privacy_demo.sh 1   # 2, 3, 4
```

У CI для інтеграційних тестів піднімається сервіс PostgreSQL (`.github/workflows/ci.yml`).

---

## 8. Поза межами програмної реалізації

Код реалізує технічні контролі; такі рішення лишаються організаційними або юридичними:
* законна підстава кожної обробки (договір, законний інтерес, згода) — у коді змодельовано лише згоду;
* строки зберігання бізнес-журналів і доказів згоди (правило RETAIN тут модельне, без автоматичного строку);
* резервні копії: анонімізація не змінює вже зроблені бекапи БД, потрібна процедура їх ротації;
* верифікація особи перед виконанням запиту суб'єкта та строк відповіді (один місяць за Art. 12(3));
* журнали й копії даних у сторонніх системах (хостинг логів, пошта), договори з обробниками (DPA), DPIA.

**Виявлені ризики поза межами ЛР4** (рекомендовано виправити окремо):
* паролі в `keys.password` зберігаються відкрито, а не хешем;
* сторінка `/forgot` показує пароль за логіном без автентифікації;
* сторінка адміністратора показує паролі користувачів.
