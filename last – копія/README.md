# Wholesale — Flask + PostgreSQL

## Швидкий старт
1. Створи БД `wholesale_db` у Postgres.
2. Виконай SQL по порядку з папки `sql/`:
   - 00_schema.sql
   - 01_seed.sql
   - 02_soft_delete.sql
   - 03_movements_cancel.sql
3. Скопіюй `.env.example` у `.env` та заповни `DATABASE_URL`.
4. Встанови залежності: `pip install -r requirements.txt`
5. Запуск: `python app.py`

## Ролі
- Admin — все + відновлення архівів, un-cancel.
- Operator — додавання/архівування/скасування.
- Authorized — перегляд, пошук.
- Guest — перегляд.
