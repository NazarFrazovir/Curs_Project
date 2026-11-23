# Architecture Decision Records

Журнал архітектурних рішень Wholesale. Правила:

* одне рішення — один файл `NNNN-коротка-назва.md`, номери не перевикористовуються;
* запис фіксується **в момент прийняття рішення** і далі **не переписується**. Змінити можна лише рядок «Статус»;
* якщо рішення застаріло, старому ADR ставимо статус `Superseded by ADR-NNNN`, а нове рішення отримує новий номер;
* шаблон: Номер · Статус · Дата · Контекст · Розглянуті альтернативи · Рішення · Наслідки.

| ADR | Рішення | Статус |
|---|---|---|
| [0001](0001-postgresql-raw-sql.md) | PostgreSQL як єдина система обліку, «сирий» SQL через psycopg2 без ORM, інваріанти в БД | Accepted |
| [0002](0002-flask-modular-monolith.md) | Модульний моноліт на Flask Blueprints із server-side rendering і вузьким JSON API | Accepted |
| [0003](0003-local-sonarqube.md) | Статичний аналіз локальним SonarQube у Docker | Superseded by ADR-0004 |
| [0004](0004-sonarcloud-instead-of-local-sonarqube.md) | SonarCloud + метрики якості в CI замість локального SonarQube | Accepted |

Шаблон нового запису:

```markdown
# ADR-NNNN: <рішення>
- **Статус:** Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- **Дата:** YYYY-MM-DD
- **Автор / власник:** …
## Контекст
## Розглянуті альтернативи
## Рішення
## Наслідки
```
