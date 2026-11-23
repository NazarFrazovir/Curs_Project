"""ЛР9, Завд.2: перевірка парсингу Sonar JSON і фінансових формул."""
import json
from datetime import date
from pathlib import Path

import pytest

from scripts import software_economics as se

REPORT = Path(__file__).resolve().parents[1] / "experiments" / "lab9" / "report.json"
ENV = {"HOURLY_RATE": "40", "OVERLOAD_COEFF": "1.3", "DISCOUNT_RATE": "0.01"}


def sonar_json(tmp_path, ncloc, sqale_index, rating="1.0"):
    payload = {"component": {"key": "demo_project", "measures": [
        {"metric": "ncloc", "value": str(ncloc)},
        {"metric": "sqale_index", "value": str(sqale_index)},
        {"metric": "sqale_rating", "value": rating},
    ]}}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_values_come_from_json_not_code():
    baseline = se.load_baseline(REPORT)
    assert baseline == se.Baseline("inventree_InvenTree", 171018, 5026, "A")


def test_sqale_passport():
    baseline = se.load_baseline(REPORT)
    assert se.debt_hours(baseline) == pytest.approx(83.767, abs=1e-3)
    assert se.debt_hours(baseline) / se.HOURS_PER_DAY == pytest.approx(10.471, abs=1e-3)
    assert se.tdd_percent(baseline) == pytest.approx(0.098, abs=1e-3)


def test_principal_and_cost_of_delay():
    baseline, config = se.load_baseline(REPORT), se.load_config(ENV)
    assert se.principal(baseline, config) == pytest.approx(5026 / 60 * 40 * 1.3)
    assert se.cost_of_delay(baseline, config) == pytest.approx(171018 / 100 * 40 * 1.3)


def test_npv_is_cumulative_and_discounted():
    baseline, config = se.load_baseline(REPORT), se.load_config(ENV)
    months = se.simulate(baseline, config)
    cod, invest = se.cost_of_delay(baseline, config), se.principal(baseline, config)
    assert [m.t for m in months] == [1, 2, 3, 4, 5, 6]
    for m in months:
        expected = sum(cod / 1.01 ** k for k in range(1, m.t + 1)) - invest
        assert m.npv == pytest.approx(expected)
    assert se.payback_month(months) == 1


def test_fail_when_debt_too_large(tmp_path):
    # 10 000 рядків, борг 1000 люд.-год: 6 міс. економії (~580 год) не покривають тіло боргу
    baseline = se.load_baseline(sonar_json(tmp_path, 10_000, 60_000, "5.0"))
    months = se.simulate(baseline, se.load_config(ENV))
    assert baseline.sqale_rating == "E"
    assert se.payback_month(months) is None
    text, status = se.render_ledger(baseline, se.load_config(ENV), months, date(2026, 11, 23))
    assert status == "FAIL" and "Архітектурне попередження" in text


def test_payback_in_later_month(tmp_path):
    # борг 300 год при 100 год/міс економії: окупність лише на 4-му місяці
    baseline = se.load_baseline(sonar_json(tmp_path, 10_000, 18_000))
    months = se.simulate(baseline, se.load_config(ENV))
    assert se.payback_month(months) == 4
    assert months[2].npv < 0 < months[3].npv


@pytest.mark.parametrize("env, message", [
    ({**ENV, "HOURLY_RATE": "20"}, "HOURLY_RATE"),
    ({k: v for k, v in ENV.items() if k != "DISCOUNT_RATE"}, "DISCOUNT_RATE"),
    ({**ENV, "OVERLOAD_COEFF": "0.5"}, "OVERLOAD_COEFF"),
])
def test_config_validation(env, message):
    with pytest.raises(ValueError, match=message):
        se.load_config(env)


def test_cli_writes_ledger(tmp_path, monkeypatch, capsys):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "FINANCIAL_LEDGER.md"
    assert se.main([str(REPORT), "--out", str(out)]) == 0
    ledger = out.read_text(encoding="utf-8")
    assert "Quality Gate): **PASS**" in ledger and "inventree_InvenTree" in ledger
    assert "леджер збережено" in capsys.readouterr().out


def test_cli_reports_missing_metric(tmp_path, monkeypatch, capsys):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    broken = tmp_path / "broken.json"
    broken.write_text('{"component": {"key": "x", "measures": []}}', encoding="utf-8")
    assert se.main([str(broken), "--out", str(tmp_path / "l.md")]) == 2
    assert "немає метрик" in capsys.readouterr().err
