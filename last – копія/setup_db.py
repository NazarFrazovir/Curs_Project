from db import get_conn

create_table_query = """
SET search_path TO app, public;

CREATE TABLE IF NOT EXISTS user_prefs (
    user_login TEXT PRIMARY KEY REFERENCES keys(login) ON DELETE CASCADE,
    theme TEXT DEFAULT 'light',
    density TEXT DEFAULT 'normal',
    per_page INTEGER DEFAULT 10,
    default_filter TEXT
);
"""

try:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(create_table_query)
        conn.commit()
        print("УСПІХ: Таблицю user_prefs створено!")
except Exception as e:
    import traceback
    traceback.print_exc()