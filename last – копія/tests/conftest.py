import os
import sys

import pytest

# Тести не повинні залежати від реальної БД: порожній DATABASE_URL
# вимикає створення пулу в db.py (load_dotenv не перезаписує вже задані змінні).
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api  # noqa: E402
from app import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    # Кожен тест стартує з порожнім кешем і без реальних пауз між повторами.
    api._cache.update(items=None, ts=None)
    monkeypatch.setattr("resilience.time.sleep", lambda s: None)
