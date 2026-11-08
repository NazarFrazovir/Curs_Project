"""ЛР6: поведінка classify_key фіксується тестами ДО експериментів зі складністю.

Ті самі тести мають проходити в усіх трьох станах: Baseline -> FAIL -> PASS (lookup table).
"""
import pytest

from privacy.sanitizer import classify_key

CASES = [
    # секрети й адреси — повне приховування
    ("password", "forbidden"), ("api_key", "forbidden"), ("session", "forbidden"),
    ("home_address", "forbidden"), ("zip", "forbidden"),
    # частково видимі значення
    ("email", "email"), ("contact_e-mail", "email"),
    ("phone", "phone"), ("mobile", "phone"), ("user_tel", "phone"),
    ("ip", "ip"), ("remote_addr", "ip"),
    ("full_name", "name"), ("login", "name"),
    # усе інше дозволено
    ("correlation_id", "allowed"), ("event", "allowed"), ("qty", "allowed"),
]


@pytest.mark.parametrize("key,expected", CASES)
def test_classify_key(key, expected):
    assert classify_key(key) == expected


def test_secret_has_priority_over_name():
    # «user_name_token» містить і name, і token — секрет важливіший
    assert classify_key("user_name_token") == "forbidden"


def test_non_string_key():
    assert classify_key(42) == "allowed"
