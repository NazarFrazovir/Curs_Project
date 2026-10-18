"""Пошук слідів значень у ВСІХ текстових/JSON-колонках схеми app.

    docker compose exec web python -m privacy.pii_scan "olena.demo" "111 22 33" "Олена Тестова"

Повертає код 1, якщо щось знайдено (зручно для перевірки після анонімізації).
"""
from __future__ import annotations

import sys

from psycopg2 import sql

from .core import transaction


def scan(cur, values) -> list:
    cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                    WHERE table_schema = 'app'
                      AND data_type IN ('text', 'character varying', 'jsonb', 'json')
                    ORDER BY table_name, column_name""")
    hits = []
    for table, column in cur.fetchall():
        for value in values:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {} WHERE {}::text ILIKE %s").format(
                    sql.Identifier("app", table), sql.Identifier(column)),
                (f"%{value}%",),
            )
            count = cur.fetchone()[0]
            if count:
                hits.append((f"{table}.{column}", value, count))
    return hits


def main(argv=None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if not values:
        print(__doc__)
        return 2
    with transaction() as cur:
        hits = scan(cur, values)
    if not hits:
        print(f"Слідів не знайдено ({len(values)} значень, усі текстові колонки схеми app).")
        return 0
    for column, value, count in hits:
        print(f"ЗНАЙДЕНО  {column:<40} '{value}'  рядків: {count}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
