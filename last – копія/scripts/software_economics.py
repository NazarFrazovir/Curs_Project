"""ЛР9, Завд.2: Software Economics — капіталізація технічного боргу (SQALE -> $).

Вхід:
  * report.json — сира відповідь SonarQube Cloud `api/measures/component`
    (метрики sqale_index, ncloc, sqale_rating);
  * змінні оточення HOURLY_RATE, OVERLOAD_COEFF, DISCOUNT_RATE.

Розрахунок:
  Principal = sqale_index / 60 * HOURLY_RATE * OVERLOAD_COEFF            — тіло боргу, $
  CoD       = ncloc / 100 * 1 год * HOURLY_RATE * OVERLOAD_COEFF          — збитки за місяць, $
  NPV_t     = sum_{k=1..t} CoD / (1 + DISCOUNT_RATE)^k  -  Principal      — кумулятивна NPV

Вихід: FINANCIAL_LEDGER.md з таблицею грошових потоків, точкою окупності
і статусом воріт якості (PASS — NPV > 0 протягом HORIZON місяців, інакше FAIL).

Запуск:
  HOURLY_RATE=40 OVERLOAD_COEFF=1.3 DISCOUNT_RATE=0.01 \
    python scripts/software_economics.py experiments/lab9/report.json
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HORIZON = 6                    # місяців після рефакторингу
LINES_PER_LOST_HOUR = 100      # 1 інженерна година втрат на 100 ncloc на місяць
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 8
WRITE_MINUTES_PER_LINE = 30    # SQALE: вартість написання 1 рядка з нуля
RATE_RANGE = (35.0, 50.0)      # допустима ставка за умовою ЛР
RATINGS = "ABCDE"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "FINANCIAL_LEDGER.md"


@dataclass(frozen=True)
class Baseline:
    key: str
    ncloc: int
    sqale_index: int        # хвилини
    sqale_rating: str       # A..E


@dataclass(frozen=True)
class Config:
    hourly_rate: float
    overload: float
    discount: float

    @property
    def loaded_rate(self):
        """Повна вартість інженерної години для компанії, $."""
        return self.hourly_rate * self.overload


@dataclass(frozen=True)
class Month:
    t: int
    factor: float           # 1 / (1 + r)^t
    cash_flow: float        # збережені збитки (CoD) за місяць
    present_value: float    # CoD * factor
    npv: float              # кумулятивна NPV


# ---------- вхідні дані ----------

def load_baseline(path):
    """Парсить сиру відповідь Sonar API: значення беруться з JSON, не з коду."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    component = data["component"]
    values = {m["metric"]: m["value"] for m in component["measures"]}
    missing = {"ncloc", "sqale_index", "sqale_rating"} - values.keys()
    if missing:
        raise ValueError(f"У {path} немає метрик: {', '.join(sorted(missing))}")
    return Baseline(
        key=component["key"],
        ncloc=int(values["ncloc"]),
        sqale_index=int(values["sqale_index"]),
        sqale_rating=rating_letter(values["sqale_rating"]),
    )


def rating_letter(value):
    """Sonar віддає рейтинг числом 1.0..5.0 — переводимо у літеру A..E."""
    return RATINGS[int(float(value)) - 1]


def env_float(name, environ):
    raw = environ.get(name)
    if raw is None:
        raise ValueError(f"Не задано змінну оточення {name}")
    return float(raw)


def load_config(environ=None):
    environ = os.environ if environ is None else environ
    config = Config(
        hourly_rate=env_float("HOURLY_RATE", environ),
        overload=env_float("OVERLOAD_COEFF", environ),
        discount=env_float("DISCOUNT_RATE", environ),
    )
    low, high = RATE_RANGE
    if not low <= config.hourly_rate <= high:
        raise ValueError(f"HOURLY_RATE має бути в діапазоні ${low:.0f}-${high:.0f}")
    if config.overload < 1 or not 0 <= config.discount < 1:
        raise ValueError("OVERLOAD_COEFF має бути >= 1, DISCOUNT_RATE — у [0; 1)")
    return config


# ---------- SQALE і фінанси ----------

def debt_hours(baseline):
    return baseline.sqale_index / MINUTES_PER_HOUR


def tdd_percent(baseline):
    """Technical Debt Density = борг (год) / час написання з нуля (год) * 100."""
    build_hours = baseline.ncloc * WRITE_MINUTES_PER_LINE / MINUTES_PER_HOUR
    return debt_hours(baseline) / build_hours * 100


def principal(baseline, config):
    """Тіло боргу: вартість повного виправлення прямо зараз, $."""
    return debt_hours(baseline) * config.loaded_rate


def cost_of_delay(baseline, config):
    """Щомісячні збитки від бездіяльності (регресійні баги), $."""
    lost_hours = baseline.ncloc / LINES_PER_LOST_HOUR
    return lost_hours * config.loaded_rate


def simulate(baseline, config, horizon=HORIZON):
    """Цикл t = 1..horizon: дисконтований грошовий потік і кумулятивна NPV."""
    invest = principal(baseline, config)
    cash_flow = cost_of_delay(baseline, config)
    months, npv = [], -invest
    for t in range(1, horizon + 1):
        factor = 1 / (1 + config.discount) ** t
        present_value = cash_flow * factor
        npv += present_value
        months.append(Month(t, factor, cash_flow, present_value, npv))
    return months


def payback_month(months):
    """Перший місяць, на якому NPV_t > 0, або None."""
    for month in months:
        if month.npv > 0:
            return month.t
    return None


# ---------- леджер ----------

def money(value):
    return f"${value:,.2f}"


def ledger_rows(months):
    yield "| Місяць t | Коеф. дисконтування 1/(1+r)^t | Щомісячний прибуток (CoD), $ | Приведена вартість, $ | Кумулятивна NPV, $ |"
    yield "|---:|---:|---:|---:|---:|"
    for m in months:
        yield (f"| {m.t} | {m.factor:.4f} | {money(m.cash_flow)} | "
               f"{money(m.present_value)} | **{money(m.npv)}** |")


def verdict(payback, horizon):
    if payback is not None:
        return (f"Точка виходу в нуль (Payback Period): окупність настає на **{payback}-му** місяці.",
                "PASS")
    return (f"За {horizon} міс. NPV не виходить у плюс: тіло боргу перевищує дисконтовану економію. "
            "⚠ Архітектурне попередження: рефакторинг треба дробити на етапи або спершу "
            "знижувати борг у гарячих точках.", "FAIL")


def render_ledger(baseline, config, months, today=None):
    today = today or date.today()
    payback = payback_month(months)
    text, status = verdict(payback, len(months))
    lines = [
        "# SOFTWARE ECONOMICS & FINANCIAL QUALITY LEDGER",
        "",
        f"_Згенеровано `scripts/software_economics.py` {today.isoformat()}_",
        "",
        "## 1. Вхідні параметри аудиту (System Baseline)",
        "",
        "| Параметр | Значення |",
        "|---|---|",
        f"| Проєкт (SonarQube Cloud key) | `{baseline.key}` |",
        f"| Масштаб системи (NCLOC) | {baseline.ncloc:,} |",
        f"| Початковий технічний борг (SQALE Index) | {baseline.sqale_index:,} хв = "
        f"{debt_hours(baseline):,.2f} люд.-год = {debt_hours(baseline) / HOURS_PER_DAY:,.2f} люд.-днів |",
        f"| TDD (щільність боргу) | {tdd_percent(baseline):.3f} % |",
        f"| Хмарний рейтинг (sqale_rating) | {baseline.sqale_rating} |",
        f"| HOURLY_RATE / OVERLOAD_COEFF / DISCOUNT_RATE | ${config.hourly_rate:g} / {config.overload:g} / {config.discount:g} |",
        "",
        "## 2. Капіталізація інвестиційних маркерів",
        "",
        "| Маркер | Формула | Значення |",
        "|---|---|---:|",
        f"| Тіло боргу (Principal, вартість рефакторингу) | sqale_index / 60 × rate × overload | **{money(principal(baseline, config))}** |",
        f"| Щомісячні збитки від бездіяльності (Cost of Delay) | ncloc / 100 × 1 год × rate × overload | **{money(cost_of_delay(baseline, config))}** |",
        "",
        f"## 3. Динаміка окупності інвестицій ({len(months)} ітерацій)",
        "",
        *ledger_rows(months),
        "",
        "## 4. Фінальний інженерно-економічний вердикт",
        "",
        text,
        "",
        f"## 5. СТАТУС ВОРІТ ЯКОСТІ (Quality Gate): **{status}**",
        "",
    ]
    return "\n".join(lines), status


def main(argv=None):
    parser = argparse.ArgumentParser(description="SQALE -> Principal, Cost of Delay, NPV")
    parser.add_argument("report", help="report.json із SonarQube Cloud API")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="шлях до FINANCIAL_LEDGER.md")
    args = parser.parse_args(argv)
    try:
        baseline, config = load_baseline(args.report), load_config()
    except (OSError, ValueError, KeyError) as error:
        print(f"[economics] помилка вхідних даних: {error}", file=sys.stderr)
        return 2
    months = simulate(baseline, config)
    text, status = render_ledger(baseline, config, months)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"[economics] {baseline.key}: Principal {money(principal(baseline, config))}, "
          f"CoD {money(cost_of_delay(baseline, config))}/міс, NPV({len(months)}) {money(months[-1].npv)}")
    print(f"[economics] Quality Gate: {status} — леджер збережено у {args.out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
