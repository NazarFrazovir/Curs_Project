"""Політика знеособлення даних у журналах (Завдання 1).

Два рівні захисту:
* redact()        — структурні дані (dict, list, DTO, dataclass, extra-поля):
                    рішення приймається за назвою поля;
* sanitize_text() — довільний текст (повідомлення, exception, JSON у рядку):
                    рішення приймається за шаблоном значення.

Обидві функції ідемпотентні: повторна обробка вже знеособленого тексту його не змінює.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
import re
import uuid
from collections.abc import Mapping

REDACTED = "[REDACTED]"
MAX_DEPTH = 6

# ---------------------------------------------------------------------------
# Політика полів: назва поля -> дія
# ---------------------------------------------------------------------------
# FORBIDDEN: значення повністю замінюється на [REDACTED]
SECRET_KEY_RE = re.compile(
    r"pass(word|wd)|pwd|secret|token|api[_-]?key|authorization|cookie|session"
    r"|credential|private[_-]?key|security[_-]?answer|(^|_)otp($|_)",
    re.IGNORECASE,
)
ADDRESS_KEY_RE = re.compile(r"(^|_)(address|street|postal_?code|zip)$", re.IGNORECASE)
# MASKED: частково видиме значення для діагностики
EMAIL_KEY_RE = re.compile(r"e-?mail", re.IGNORECASE)
PHONE_KEY_RE = re.compile(r"phone|mobile|msisdn|(^|_)tel$", re.IGNORECASE)
IP_KEY_RE = re.compile(r"(^|_)(ip|ip_?addr(ess)?|remote_?addr|client_?ip)$", re.IGNORECASE)
NAME_KEY_RE = re.compile(
    r"(^|_)(full_?name|first_?name|last_?name|name|login|user_?name)$", re.IGNORECASE
)
# Усі інші поля (correlation_id, event, result, actor, subject, лічильники...) — ALLOWED.

LOG_FIELD_POLICY = {
    "FORBIDDEN (→ [REDACTED])": "password, *_token, api_key, secret, session, cookie, "
                                "authorization, credential, security_answer, otp, address",
    "MASKED (частково)": "email → o***@example.com; phone → +**********33; "
                         "ip → 192.168.x.x; full_name/name/login → О***",
    "ALLOWED": "correlation_id, event, result, actor/subject (user:<id>), "
               "типи операцій, лічильники, коди помилок",
}

# ---------------------------------------------------------------------------
# Шаблони для довільного тексту
# ---------------------------------------------------------------------------
_KNOWN_SECRETS: set = set()

_URL_CREDENTIALS_RE = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@", re.IGNORECASE)
_AUTH_SCHEME_RE = re.compile(r"\b(Bearer|Basic|Token)\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]{6,}",
                             re.IGNORECASE)
# JWT та підписані cookie itsdangerous (сесія Flask): три сегменти base64url
_JWT_RE = re.compile(r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}")
_KV_SECRET_RE = re.compile(
    r"""(?P<key>["']?[\w-]*(?:pass(?:word|wd)|pwd|secret|token|api[_-]?key|authorization"""
    r"""|cookie|session|credential)[\w-]*["']?)"""
    r"""(?P<sep>\s*[:=]\s*)"""
    r"""(?P<val>"[^"]*"|'[^']*'|(?:(?:Bearer|Basic|Token)\s+)?(?:\[REDACTED\]|[^\s,;&)}\]"']+))""",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(
    r"(?<![\w.+%-])([A-Za-z0-9][A-Za-z0-9._%+-]*)@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})"
)
_QUERY_PARAM_RE = re.compile(r"([?&])([\w.\[\]-]+)=([^&\s\"'#]*)")
SAFE_QUERY_PARAMS = {"page", "per_page", "sort", "order", "show_zero", "tab", "format"}
_IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
_PHONE_RE = re.compile(
    r"(?<![\w+*])"
    r"(?:\+\d[\d\s().-]{8,20}\d"                                 # міжнародний: +380 00 111 22 33
    r"|\(?0\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"            # національний: 000 111 22 33
    r"|380\d{9})"                                                # без плюса: 380001112233
    r"(?!\w)"
)


def register_secret(value) -> None:
    """Зареєструвати конкретне значення секрету (SECRET_KEY, пароль БД тощо).

    Будь-яка його поява в журналі буде замінена на [REDACTED]. Короткі значення
    ігноруються, щоб не псувати звичайні числа й слова.
    """
    if isinstance(value, str) and len(value) >= 8:
        _KNOWN_SECRETS.add(value)


def mask_email(value: str) -> str:
    local, sep, domain = str(value).partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def _already_masked(value) -> bool:
    return "*" in str(value) or str(value).endswith(".x.x") or str(value) == REDACTED


def mask_phone(value: str) -> str:
    if _already_masked(value):
        return str(value)
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 4:
        return "***"
    prefix = "+" if str(value).strip().startswith("+") else ""
    return prefix + "*" * (len(digits) - 2) + digits[-2:]


def mask_ip(value: str) -> str:
    if _already_masked(value):
        return str(value)
    m = _IPV4_RE.fullmatch(str(value).strip())
    if not m:
        return "***"
    return f"{m.group(1)}.{m.group(2)}.x.x"


def mask_name(value: str) -> str:
    value = str(value).strip()
    return f"{value[0]}***" if value else "***"


def _replace_kv(m: re.Match) -> str:
    val = m.group("val")
    quote = val[0] if val[:1] in ("'", '"') else ""
    return f"{m.group('key')}{m.group('sep')}{quote}{REDACTED}{quote}"


def _replace_email(m: re.Match) -> str:
    return f"{m.group(1)[0]}***@{m.group(2)}"


def _replace_query(m: re.Match) -> str:
    key = m.group(2)
    if key.lower() in SAFE_QUERY_PARAMS:
        return m.group(0)
    return f"{m.group(1)}{key}={REDACTED}"


def _replace_ip(m: re.Match) -> str:
    if all(int(part) <= 255 for part in m.groups()):
        return f"{m.group(1)}.{m.group(2)}.x.x"
    return m.group(0)


def _replace_phone(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if 10 <= len(digits) <= 15:
        return mask_phone(m.group(0))
    return m.group(0)


def sanitize_text(text) -> str:
    """Знеособити довільний текст. Порядок важливий: спершу секрети, потім ідентифікатори."""
    if not isinstance(text, str):
        text = str(text)
    for secret in sorted(_KNOWN_SECRETS, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    text = _URL_CREDENTIALS_RE.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)
    text = _AUTH_SCHEME_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _KV_SECRET_RE.sub(_replace_kv, text)
    text = _EMAIL_RE.sub(_replace_email, text)
    text = _QUERY_PARAM_RE.sub(_replace_query, text)
    text = _IPV4_RE.sub(_replace_ip, text)
    text = _PHONE_RE.sub(_replace_phone, text)
    return text


# ---------------------------------------------------------------------------
# Структурні дані
# ---------------------------------------------------------------------------
class RedactedObject:
    """Знеособлене представлення DTO: зберігає назву типу для діагностики."""

    __slots__ = ("type_name", "fields")

    def __init__(self, type_name: str, fields: dict):
        self.type_name = type_name
        self.fields = fields

    def as_dict(self) -> dict:
        return {"__type__": self.type_name, **self.fields}

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}={v!r}" for k, v in self.fields.items())
        return f"{self.type_name}({inner})"

    __str__ = __repr__


_SAFE_SCALARS = (bool, int, float, decimal.Decimal, _dt.date, _dt.time, _dt.timedelta, uuid.UUID)


def classify_key(key) -> str:
    key = str(key)
    if SECRET_KEY_RE.search(key) or ADDRESS_KEY_RE.search(key):
        return "forbidden"
    if EMAIL_KEY_RE.search(key):
        return "email"
    if PHONE_KEY_RE.search(key):
        return "phone"
    if IP_KEY_RE.search(key):
        return "ip"
    if NAME_KEY_RE.search(key):
        return "name"
    return "allowed"


_MASKERS = {"email": mask_email, "phone": mask_phone, "ip": mask_ip, "name": mask_name}


def redact(value, key=None, _depth: int = 0):
    """Рекурсивно знеособити значення. key — назва поля, якому належить value."""
    if key is not None:
        rule = classify_key(key)
        if rule == "forbidden":
            return REDACTED
        if rule in _MASKERS and value is not None and not isinstance(value, (Mapping, list, tuple)):
            return _MASKERS[rule](value)
    if value is None or isinstance(value, _SAFE_SCALARS):
        return value
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "[BINARY]"
    if _depth >= MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, RedactedObject):
        return value
    if isinstance(value, Mapping):
        return {k: redact(v, k, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [redact(v, None, _depth + 1) for v in value]
        return tuple(items) if isinstance(value, tuple) else items
    if isinstance(value, BaseException):
        return sanitize_text(str(value))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        raw = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
        return RedactedObject(type(value).__name__, redact(raw, None, _depth + 1))
    if hasattr(value, "__dict__") and not isinstance(value, type) and not callable(value):
        return RedactedObject(type(value).__name__, redact(dict(vars(value)), None, _depth + 1))
    return sanitize_text(str(value))
