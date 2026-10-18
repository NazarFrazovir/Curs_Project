"""Централізоване безпечне логування (Завдання 1).

Точка інтеграції — фабрика LogRecord (logging.setLogRecordFactory). Через неї
проходить КОЖЕН запис журналу в процесі: з будь-якого модуля, логера Flask,
werkzeug чи gunicorn, з повідомлення, аргументів чи exception. Тому окремий
controller не може «забути» замаскувати дані.

Додатково:
* PiiFilter на handler'ах обробляє extra-поля (їх logging додає вже після фабрики)
  і записи, створені в обхід фабрики (logging.makeLogRecord);
* форматери text/JSON роблять фінальну перевірку вже сформованого рядка.
"""
from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging
import os
import sys
import uuid
from contextlib import contextmanager
from urllib.parse import urlparse

from .sanitizer import RedactedObject, redact, register_secret, sanitize_text

_correlation_id = contextvars.ContextVar("correlation_id", default="-")
_traceback_formatter = logging.Formatter()

# Стандартні атрибути LogRecord: усе інше — extra-поля, передані розробником
_STANDARD_ATTRS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", (), None))) | {
    "message", "asctime", "correlation_id", "taskName",
}


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------
def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value=None):
    """Встановити correlation ID поточного контексту; повертає token для reset."""
    return _correlation_id.set(value or uuid.uuid4().hex)


def reset_correlation_id(token) -> None:
    _correlation_id.reset(token)


@contextmanager
def correlation_scope(value=None):
    """Для фонових задач і скриптів: усі записи всередині отримають один correlation ID."""
    token = set_correlation_id(value)
    try:
        yield get_correlation_id()
    finally:
        reset_correlation_id(token)


# ---------------------------------------------------------------------------
# Знеособлення одного запису
# ---------------------------------------------------------------------------
def _redact_args(args):
    if isinstance(args, dict):
        return redact(args)
    if isinstance(args, tuple):
        return tuple(redact(a) for a in args)
    return redact(args)


def sanitize_record(record: logging.LogRecord) -> logging.LogRecord:
    """Знеособити повідомлення, аргументи, traceback і stack.

    Функція ідемпотентна, тому повторний виклик (фабрика + фільтр handler'а) безпечний.
    Прапорця «вже оброблено» навмисно немає: logging.makeLogRecord створює запис
    через фабрику, а ПОТІМ підставляє сирі msg/args — прапорець би їх пропустив.
    """
    try:
        if not isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = _redact_args(record.args)
        try:
            message = record.getMessage()
        except Exception:  # некоректні аргументи форматування не повинні ламати лог
            message = f"{record.msg} [unformattable args]"
        record.msg = sanitize_text(message)
        record.args = None
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = _traceback_formatter.formatException(record.exc_info)
            record.exc_info = None  # жоден інший форматер не відрендерить сирий exception
        if record.exc_text:
            record.exc_text = sanitize_text(record.exc_text)
        if record.stack_info:
            record.stack_info = sanitize_text(record.stack_info)
    except Exception:
        record.msg = "[log record dropped: sanitization error]"
        record.args = None
        record.exc_info = None
        record.exc_text = None
    return record


def sanitize_extras(record: logging.LogRecord) -> None:
    for key in list(vars(record)):
        if key not in _STANDARD_ATTRS and not key.startswith("_"):
            setattr(record, key, redact(getattr(record, key), key))


class PiiFilter(logging.Filter):
    """Фільтр для handler'ів: extra-поля + записи, що оминули фабрику."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id()
        sanitize_record(record)
        if not getattr(record, "_pii_extras_safe", False):
            sanitize_extras(record)
            record._pii_extras_safe = True
        return True


# ---------------------------------------------------------------------------
# Фабрика записів — головна точка інтеграції
# ---------------------------------------------------------------------------
def install_record_factory() -> None:
    current = logging.getLogRecordFactory()
    if getattr(current, "_pii_sanitizing", False):
        return

    def factory(*args, **kwargs):
        record = current(*args, **kwargs)
        record.correlation_id = get_correlation_id()
        return sanitize_record(record)

    factory._pii_sanitizing = True
    factory._wrapped = current
    logging.setLogRecordFactory(factory)


def uninstall_record_factory() -> None:
    """Лише для тестів: повернути стандартну фабрику."""
    current = logging.getLogRecordFactory()
    while getattr(current, "_pii_sanitizing", False):
        current = current._wrapped
    logging.setLogRecordFactory(current)


# ---------------------------------------------------------------------------
# Форматери
# ---------------------------------------------------------------------------
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [cid=%(correlation_id)s] %(message)s"


class SafeTextFormatter(logging.Formatter):
    def __init__(self, fmt: str = TEXT_FORMAT):
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id()
        return sanitize_text(super().format(record))


def _json_default(obj):
    if isinstance(obj, RedactedObject):
        return obj.as_dict()
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    return str(obj)


class SafeJsonFormatter(logging.Formatter):
    """Структурований лог: один JSON-об'єкт на рядок."""

    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "ts": _dt.datetime.fromtimestamp(record.created, _dt.timezone.utc)
                  .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", get_correlation_id()),
            "message": record.getMessage(),
        }
        extras = {k: v for k, v in vars(record).items()
                  if k not in _STANDARD_ATTRS and not k.startswith("_")}
        if extras:
            doc["fields"] = extras
        if record.exc_text or record.exc_info:
            doc["exception"] = record.exc_text or self.formatException(record.exc_info)
        # фінальна перевірка структури (а не рядка), щоб не зламати JSON
        return json.dumps(redact(doc), ensure_ascii=False, default=_json_default)


# ---------------------------------------------------------------------------
# Налаштування застосунку
# ---------------------------------------------------------------------------
def register_secrets_from_env() -> None:
    for name in ("SECRET_KEY", "POSTGRES_PASSWORD", "GITHUB_TOKEN", "SONAR_TOKEN"):
        register_secret(os.environ.get(name))
    url = os.environ.get("DATABASE_URL")
    if url:
        register_secret(urlparse(url).password)


def _attach_filter(handler: logging.Handler) -> None:
    if not any(isinstance(f, PiiFilter) for f in handler.filters):
        handler.addFilter(PiiFilter())


def configure_logging(level=None, fmt=None, stream=None) -> logging.Handler:
    """Замінює logging.basicConfig: єдиний безпечний handler для всього процесу.

    LOG_FORMAT=text|json, LOG_LEVEL=INFO|DEBUG|...
    """
    level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    fmt = (fmt or os.environ.get("LOG_FORMAT", "text")).lower()

    install_record_factory()
    register_secrets_from_env()

    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_pii_safe_handler", False):
            root.removeHandler(h)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler._pii_safe_handler = True
    handler.setFormatter(SafeJsonFormatter() if fmt == "json" else SafeTextFormatter())
    handler.addFilter(PiiFilter())
    root.addHandler(handler)
    root.setLevel(level)

    # handler'и, створені не нами (gunicorn, старий basicConfig), теж отримують фільтр
    for name in ("", "gunicorn.error", "gunicorn.access", "werkzeug"):
        for h in logging.getLogger(name).handlers:
            _attach_filter(h)
    return handler
