"""Синтетичні суб'єкти для демонстрації й тестів ЛР4.

    python -m privacy.demo_seed      # створити / відновити olena.demo і petro.demo

Жодних реальних даних: домен example.com зарезервований (RFC 2606), код
оператора «00» в Україні не існує, паролі придумані лише для демо.
Після анонімізації olena.demo скрипт просто створює її заново (новий id).
"""
from __future__ import annotations

from psycopg2.extras import Json

DEMO_USERS = [
    {"login": "olena.demo", "password": "demo-pass-1", "role": "Authorized",
     "full_name": "Олена Тестова", "email": "olena.demo@example.com", "phone": "+380 00 111 22 33"},
    {"login": "petro.demo", "password": "demo-pass-2", "role": "Authorized",
     "full_name": "Петро Тестовий", "email": "petro.demo@example.com", "phone": "+380 00 444 55 66"},
]


def create_subject(cur, login, password, role, full_name, email, phone, with_history=True) -> int:
    """Створити (або оновити) користувача з даними в усіх пов'язаних джерелах."""
    cur.execute(
        """INSERT INTO keys (login, password, role, full_name, email, phone, account_status)
           VALUES (%s, %s, %s, %s, %s, %s, 'active')
           ON CONFLICT (login) DO UPDATE
              SET password = EXCLUDED.password, role = EXCLUDED.role,
                  full_name = EXCLUDED.full_name, email = EXCLUDED.email,
                  phone = EXCLUDED.phone, account_status = 'active'
        RETURNING id""",
        (login, password, role, full_name, email, phone),
    )
    user_id = cur.fetchone()[0]
    cur.execute("UPDATE keys SET last_login = now() - interval '1 day' WHERE id = %s", (user_id,))
    cur.execute(
        """INSERT INTO user_prefs (user_login, theme, density, per_page, default_filter, updated_by)
           VALUES (%s, 'light', 'compact', 50, %s, %s)
           ON CONFLICT (user_login) DO UPDATE
              SET theme = 'light', density = 'compact', per_page = 50,
                  default_filter = EXCLUDED.default_filter""",
        (login, Json({"supplier": "Демо-постачальник"}), login),
    )
    if not with_history:
        return user_id

    cur.execute("SELECT 1 FROM access_requests WHERE user_id = %s", (user_id,))
    if cur.fetchone() is None:
        # вільний текст із PII — типова «прихована» копія даних, яку треба знайти при видаленні
        cur.execute(
            """INSERT INTO access_requests (user_id, message, status, processed_at, processed_by, admin_comment)
               VALUES (%s, %s, 'approved', now(), 'admin', %s)""",
            (user_id, f"Прошу надати доступ. Мій телефон для зв'язку: {phone}",
             f"Погоджено, підтвердження надіслано на {email}"),
        )
    cur.execute("SELECT 1 FROM archive_history WHERE performed_by = %s", (login,))
    if cur.fetchone() is None:
        cur.execute(
            """INSERT INTO archive_history (entity_type, entity_id, action, performed_by, reason)
               VALUES ('customer', 1, 'archive', %s, 'Демо: контрагент призупинив співпрацю'),
                      ('customer', 1, 'restore', %s, NULL)""",
            (login, login),
        )
    return user_id


def reset_consents(cur, user_id: int) -> None:
    """Для повторення демо: коректно відкликати згоди (історія при цьому зберігається)."""
    from .consent import PURPOSES, revoke
    for code in PURPOSES:
        revoke(cur, user_id, code, source="demo_reset")


def main() -> int:
    from .core import transaction
    from .logging_setup import configure_logging
    configure_logging()
    with transaction() as cur:
        for user in DEMO_USERS:
            user_id = create_subject(cur, **user)
            reset_consents(cur, user_id)
            print(f"{user['login']:<12} id={user_id:<5} пароль: {user['password']}")
    return 0


if __name__ == "__main__":
    # запускати там, де задано DATABASE_URL:  docker compose exec web python -m privacy.demo_seed
    raise SystemExit(main())
