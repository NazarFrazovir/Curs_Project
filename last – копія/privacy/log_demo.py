"""Демонстрація Кроку 1 (Secure Logging) на синтетичних даних.

    python -m privacy.log_demo            # захищений журнал, текстовий формат
    python -m privacy.log_demo --json     # захищений журнал, структурований JSON
    python -m privacy.log_demo --unsafe   # «ДО»: стандартний logging без захисту (для звіту)

Усі значення вигадані: домен example.com зарезервований, код оператора 00 не існує.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass

from .logging_setup import configure_logging, correlation_scope, uninstall_record_factory

SYNTHETIC = {
    "full_name": "Олена Тестова",
    "email": "olena.demo@example.com",
    "phone": "+380 00 111 22 33",
    "password": "Demo-Passw0rd!",
    "api_token": "tok_demo_9f8e7d6c5b4a3210",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkZW1vIn0.ZGVtby1zaWduYXR1cmU",  # gitleaks:allow — синтетичний токен для демо
}


@dataclass
class Credentials:
    password: str
    api_token: str


@dataclass
class RegistrationRequest:
    full_name: str
    email: str
    phone: str
    credentials: Credentials


class UserAlreadyExists(Exception):
    pass


def register_user(dto: RegistrationRequest, log: logging.Logger) -> None:
    """Операція, що обробляє email, телефон, пароль і токен — усі типові «пастки»."""
    # 1. вкладений DTO як аргумент повідомлення
    log.info("registration started: %s", dto)
    # 2. значення прямо в тексті повідомлення
    log.info("sending confirmation to %s, sms to %s, Authorization: Bearer %s",
             dto.email, dto.phone, SYNTHETIC["jwt"])
    # 3. серіалізований JSON у рядку
    log.info("payload %s", json.dumps({"email": dto.email, "password": dto.credentials.password,
                                       "api_token": dto.credentials.api_token}))
    # 4. структуровані поля (extra) — видно у форматі JSON
    log.info("user.registered", extra={"event": "user.registered", "result": "pending",
                                       "email": dto.email, "phone": dto.phone,
                                       "credentials": dto.credentials})
    # 5. повідомлення exception з PII та секретом
    try:
        raise UserAlreadyExists(
            f"user {dto.email} already exists (password={dto.credentials.password})")
    except UserAlreadyExists:
        log.exception("registration failed")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    unsafe = "--unsafe" in argv
    fmt = "json" if "--json" in argv else "text"

    if unsafe:
        uninstall_record_factory()
        for h in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(h)
        logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        print("=== ДО: стандартний logging без захисту ===")
    else:
        configure_logging(fmt=fmt, stream=sys.stdout)
        print(f"=== ПІСЛЯ: централізований захист, формат {fmt} ===")

    dto = RegistrationRequest(SYNTHETIC["full_name"], SYNTHETIC["email"], SYNTHETIC["phone"],
                              Credentials(SYNTHETIC["password"], SYNTHETIC["api_token"]))
    with correlation_scope("demo-req-0001"):
        register_user(dto, logging.getLogger("app.registration"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
