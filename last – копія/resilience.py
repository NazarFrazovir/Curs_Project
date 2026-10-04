"""Механізм стійкості: Retry з обмеженою кількістю спроб та exponential backoff + jitter.

Параметри винесені в змінні середовища, щоб їх можна було змінювати без зміни коду.
"""
import logging
import os
import random
import time

import psycopg2

log = logging.getLogger("resilience")

# 3 спроби = 1 основна + 2 повтори. Більше не має сенсу: якщо БД не відповіла
# тричі поспіль, це вже не короткий збій, а відмова, і подальші повтори лише
# додають навантаження на залежність, яка й так не справляється (retry storm).
RETRY_ATTEMPTS = int(os.environ.get("DB_RETRY_ATTEMPTS", "3"))
# Перша пауза ~100 мс, далі подвоюється (100 → 200 мс), але не більше 1 с.
RETRY_BASE_DELAY = float(os.environ.get("DB_RETRY_BASE_DELAY", "0.1"))
RETRY_MAX_DELAY = float(os.environ.get("DB_RETRY_MAX_DELAY", "1.0"))

# Повторюємо лише тимчасові помилки з'єднання. Помилки SQL, валідації чи
# вичерпаного пулу (PoolError) не повторюються: повтор їх не виправить,
# а при перевантаженні лише погіршить ситуацію.
TRANSIENT_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def backoff_delay(attempt, base_delay=None, max_delay=None):
    """Пауза перед повтором № attempt (1, 2, ...): exponential backoff + equal jitter.

    Половина паузи фіксована, половина випадкова — так клієнти, що впали
    одночасно, не повторюють запити синхронно (thundering herd).
    """
    base = RETRY_BASE_DELAY if base_delay is None else base_delay
    cap = RETRY_MAX_DELAY if max_delay is None else max_delay
    delay = min(cap, base * (2 ** (attempt - 1)))
    return delay / 2 + random.uniform(0, delay / 2)


def call_with_retry(func, attempts=None, sleep=None):
    """Викликає func() і повторює її при тимчасових помилках БД.

    Після останньої невдалої спроби пробрасує помилку далі — рішення про
    fallback приймає викликач.
    """
    attempts = RETRY_ATTEMPTS if attempts is None else attempts
    sleep = sleep or time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except TRANSIENT_ERRORS as exc:
            if attempt == attempts:
                log.error("DB call failed after %d attempts: %s", attempts, exc)
                raise
            delay = backoff_delay(attempt)
            log.warning("DB call failed (attempt %d/%d): %s; retry in %.2fs",
                        attempt, attempts, exc, delay)
            sleep(delay)
