"""Завдання 1. Secure Logging: перевіряється ФАКТИЧНИЙ output логера.

Тести не потребують БД. Кожен перевіряє, що жодне вихідне sensitive-значення
не з'явилось у журналі, а діагностичні дані (операція, correlation ID) лишились.
"""
import io
import json
import logging

import pytest

from privacy.log_demo import SYNTHETIC, Credentials, RegistrationRequest, register_user
from privacy.logging_setup import (PiiFilter, SafeTextFormatter, configure_logging,
                                   correlation_scope, install_record_factory,
                                   uninstall_record_factory)
from privacy.sanitizer import REDACTED, register_secret, sanitize_text

# Значення, яких НЕ повинно бути в журналі у відкритому вигляді
SENSITIVE = {
    "email": SYNTHETIC["email"],
    "email_local_part": "olena.demo",
    "phone": SYNTHETIC["phone"],
    "phone_tail": "111 22 33",
    "full_name": SYNTHETIC["full_name"],
    "password": SYNTHETIC["password"],
    "api_token": SYNTHETIC["api_token"],
    "jwt": SYNTHETIC["jwt"],
}


def assert_no_leak(output: str, sensitive: dict = SENSITIVE) -> None:
    """FAIL, якщо хоча б одне вихідне значення є в тексті журналу."""
    leaked = sorted(name for name, value in sensitive.items() if value in output)
    assert not leaked, f"у журнал потрапили відкриті значення: {leaked}"


def make_dto() -> RegistrationRequest:
    return RegistrationRequest(SYNTHETIC["full_name"], SYNTHETIC["email"], SYNTHETIC["phone"],
                               Credentials(SYNTHETIC["password"], SYNTHETIC["api_token"]))


@pytest.fixture
def capture_log():
    """Перенаправляє єдиний безпечний handler застосунку в буфер і відновлює після тесту."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level

    def _capture(fmt="text"):
        buf = io.StringIO()
        configure_logging(fmt=fmt, stream=buf)
        return buf

    yield _capture
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)
    install_record_factory()


# ---------------------------------------------------------------------------
# Позитивні сценарії
# ---------------------------------------------------------------------------
def test_text_log_masks_identifiers_and_redacts_secrets(capture_log):
    buf = capture_log("text")
    with correlation_scope("test-cid-0001"):
        register_user(make_dto(), logging.getLogger("app.registration"))
    out = buf.getvalue()

    assert_no_leak(out)
    assert "o***@example.com" in out              # email частково видно
    assert "+**********33" in out                 # телефон: лише 2 останні цифри
    assert out.count(REDACTED) >= 5               # пароль, токени, JWT, credentials
    # діагностична цінність збережена
    assert "registration started" in out and "registration failed" in out
    assert "[cid=test-cid-0001]" in out
    assert "UserAlreadyExists" in out             # тип помилки й traceback лишились


def test_json_log_is_valid_structured_and_sanitized(capture_log):
    buf = capture_log("json")
    with correlation_scope("test-cid-0002"):
        register_user(make_dto(), logging.getLogger("app.registration"))
    out = buf.getvalue()

    assert_no_leak(out)
    records = [json.loads(line) for line in out.splitlines()]   # формат не зруйновано
    assert {r["correlation_id"] for r in records} == {"test-cid-0002"}
    event = next(r for r in records if r["message"] == "user.registered")
    assert event["fields"]["event"] == "user.registered"
    assert event["fields"]["email"] == "o***@example.com"
    assert event["fields"]["phone"] == "+**********33"
    assert event["fields"]["credentials"] == REDACTED
    failure = next(r for r in records if r["level"] == "ERROR")
    assert "UserAlreadyExists" in failure["exception"]


def test_every_logger_in_process_is_covered(capture_log):
    """Захист не залежить від модуля: Flask, werkzeug, gunicorn, власні логери."""
    buf = capture_log("text")
    for name in ("auth", "inventory", "werkzeug", "flask.app"):
        logging.getLogger(name).warning("user %s phone %s", SYNTHETIC["email"], SYNTHETIC["phone"])
    # рядок access-логу: пошук за email у query string
    logging.getLogger("werkzeug").info(
        '127.0.0.1 - - "GET /admin/users?q=%s&page=2 HTTP/1.1" 200 -', SYNTHETIC["email"])
    out = buf.getvalue()
    assert_no_leak(out)
    assert "page=2" in out and "127.0.x.x" in out


# ---------------------------------------------------------------------------
# Негативні сценарії: вкладені DTO, exception message, обхід фабрики
# ---------------------------------------------------------------------------
def test_nested_dto_and_containers_are_redacted(capture_log):
    buf = capture_log("json")
    payload = {"batch": [{"user": make_dto(), "meta": {"session_token": SYNTHETIC["jwt"]}}],
               "contact": (SYNTHETIC["email"], SYNTHETIC["phone"])}
    log = logging.getLogger("app.batch")
    log.info("batch %s", payload)
    log.info("batch.extra", extra={"payload": payload})
    out = buf.getvalue()
    assert_no_leak(out)
    assert "RegistrationRequest" in out           # тип DTO лишився для діагностики


def test_exception_messages_and_chained_causes_are_sanitized(capture_log):
    buf = capture_log("text")
    log = logging.getLogger("app.errors")
    try:
        try:
            raise ConnectionError(f"smtp rejected {SYNTHETIC['email']} token={SYNTHETIC['api_token']}")
        except ConnectionError as inner:
            raise RuntimeError(f"cannot notify {SYNTHETIC['phone']}: password={SYNTHETIC['password']}") from inner
    except RuntimeError as exc:
        log.exception("notification failed")
        log.error("notification failed again: %s", exc)
        log.error("as repr: %r", exc)
    out = buf.getvalue()
    assert_no_leak(out)
    assert "ConnectionError" in out and "RuntimeError" in out


def test_record_created_outside_factory_is_still_sanitized():
    """logging.makeLogRecord оминає фабрику — його обробляє PiiFilter на handler'і."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(SafeTextFormatter())
    handler.addFilter(PiiFilter())
    record = logging.makeLogRecord({
        "name": "remote", "levelno": logging.INFO, "levelname": "INFO",
        "msg": "remote says %s password=%s", "args": (SYNTHETIC["email"], SYNTHETIC["password"]),
        "password": SYNTHETIC["password"],
    })
    handler.handle(record)
    assert_no_leak(buf.getvalue())
    assert record.password == REDACTED


def test_leak_detector_fails_without_protection():
    """Контроль самого тесту: без захисту assert_no_leak ПАДАЄ (тест не «завжди зелений»)."""
    buf = io.StringIO()
    plain = logging.StreamHandler(buf)
    log = logging.getLogger("unprotected.demo")
    log.addHandler(plain)
    log.propagate = False
    uninstall_record_factory()
    try:
        log.warning("user %s password=%s", SYNTHETIC["email"], SYNTHETIC["password"])
    finally:
        install_record_factory()
        log.removeHandler(plain)
    with pytest.raises(AssertionError, match="email"):
        assert_no_leak(buf.getvalue())


# ---------------------------------------------------------------------------
# Правила sanitizer
# ---------------------------------------------------------------------------
def test_sanitizer_keeps_technical_data_and_is_idempotent():
    text = ("2026-10-18 22:10:05,123 op=export cid=0e8f1c2d-1234-4123-8123-123456789012 "
            "result=success subject=user:7 took 15ms rows=1234567")
    assert sanitize_text(text) == text
    once = sanitize_text(f"{SYNTHETIC['email']} {SYNTHETIC['phone']} password={SYNTHETIC['password']}")
    assert sanitize_text(once) == once


def test_url_credentials_and_registered_secrets_are_redacted():
    register_secret("unit-test-secret-key-123")
    out = sanitize_text("dsn=postgresql://app:db-pass-123@db:5432/x key unit-test-secret-key-123")
    assert "db-pass-123" not in out and "unit-test-secret-key-123" not in out
    assert "postgresql://app:[REDACTED]@db:5432/x" in out
