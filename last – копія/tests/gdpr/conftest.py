"""Інфраструктура інтеграційних тестів ЛР4: справжня PostgreSQL.

Запуск:
    TEST_DATABASE_URL=postgresql://postgres:<пароль>@localhost:5433/wholesale_test pytest tests/gdpr -v

Схема app у тестовій БД перестворюється з нуля з усіх sql/*.sql — так перевіряється,
що механізми працюють на чистій базі. Тому назва БД ОБОВ'ЯЗКОВО має містити «test».
Без TEST_DATABASE_URL інтеграційні тести пропускаються, тести логування — працюють.
"""
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import pool

import db
from app import create_app
from privacy.demo_seed import create_subject

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


@pytest.fixture(scope="session")
def pg_pool():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL не задано — інтеграційні тести ЛР4 потребують PostgreSQL")
    conn = psycopg2.connect(TEST_DATABASE_URL)
    if "test" not in conn.info.dbname:
        conn.close()
        pytest.exit("TEST_DATABASE_URL має вказувати на окрему тестову БД (у назві 'test'): "
                    "схема app у ній буде видалена й створена заново", returncode=2)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS app CASCADE")
        for script in sorted(SQL_DIR.glob("*.sql")):
            cur.execute(script.read_text(encoding="utf-8"))
    conn.close()
    p = pool.SimpleConnectionPool(1, 8, dsn=TEST_DATABASE_URL)
    yield p
    p.closeall()


@pytest.fixture
def pg(pg_pool, monkeypatch):
    """Застосунок працює з тестовою БД (db.POOL читається під час кожного запиту)."""
    monkeypatch.setattr(db, "POOL", pg_pool)
    return pg_pool


class Sql:
    def __init__(self, p):
        self.pool = p

    def _run(self, query, params, fetch):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO app, public")
                cur.execute(query, params)
                result = fetch(cur) if cur.description else None
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def one(self, query, params=()):
        return self._run(query, params, lambda c: c.fetchone())

    def all(self, query, params=()):
        return self._run(query, params, lambda c: c.fetchall())

    def value(self, query, params=()):
        row = self.one(query, params)
        return row[0] if row else None

    def exec(self, query, params=()):
        self._run(query, params, lambda c: None)

    def find_everywhere(self, values: dict) -> list:
        """Шукає кожне значення в УСІХ текстових/JSON-колонках схеми app.
        Повертає [(таблиця.колонка, назва_значення)] — порожньо, якщо слідів немає."""
        columns = self.all("""SELECT table_name, column_name FROM information_schema.columns
                               WHERE table_schema = 'app'
                                 AND data_type IN ('text', 'character varying', 'jsonb', 'json')""")
        found = []
        for table, column in columns:
            for name, value in values.items():
                hit = self.value(
                    f'SELECT 1 FROM app."{table}" WHERE "{column}"::text ILIKE %s LIMIT 1',
                    (f"%{value}%",))
                if hit:
                    found.append((f"{table}.{column}", name))
        return found


@pytest.fixture
def sql(pg):
    return Sql(pg)


@dataclass
class TestUser:
    id: int
    login: str
    password: str
    full_name: str
    email: str
    phone: str
    role: str

    __test__ = False  # не колекціонувати як тест-клас

    def pii(self) -> dict:
        return {"login": self.login, "email": self.email, "phone": self.phone,
                "full_name": self.full_name}


@pytest.fixture
def make_user(sql):
    """Синтетичний користувач з даними в профілі, налаштуваннях, заявках і журналі дій."""
    def _make(role="Authorized", with_history=True) -> TestUser:
        tag = uuid.uuid4().hex[:8]
        n = int(tag, 16)
        user = TestUser(
            id=0, login=f"t-{tag}", password=f"pw-{tag}-Synthetic", role=role,
            full_name=f"Тестовий Користувач {tag}",
            email=f"user.{tag}@example.com",
            phone=f"+380 00 {n % 1000:03d} {n // 1000 % 100:02d} {n // 100000 % 100:02d}",
        )
        conn = sql.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO app, public")
                user.id = create_subject(cur, user.login, user.password, role, user.full_name,
                                         user.email, user.phone, with_history=with_history)
            conn.commit()
        finally:
            sql.pool.putconn(conn)
        return user
    return _make


@pytest.fixture
def login_as(pg):
    """Окремий HTTP-клієнт із сесією вказаного користувача (через справжній /login)."""
    def _login(user: TestUser):
        client = create_app().test_client()
        resp = client.post("/login", data={"login": user.login, "password": user.password})
        assert resp.status_code == 302
        with client.session_transaction() as s:
            assert s.get("user", {}).get("login") == user.login, "вхід не вдався"
        return client
    return _login


@pytest.fixture
def anonymous_client(pg):
    return create_app().test_client()
