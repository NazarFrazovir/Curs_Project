"""ЛР5: відтворюваний збір статичних метрик (lizard / radon / complexipy / ruff).

Принципи (з висновків Reliability Test):
  1. Версії інструментів записуються в результат — число без версії сканера не порівнюється.
  2. Будь-яка помилка інструмента = FAIL збору (exit 2), а не «менше проблем».
     Інакше файл, який сканер не зміг прочитати, тихо випадає зі статистики.
  3. Набір правил ruff фіксований (--isolated), не залежить від локальних конфігів.

Використання:
  python scripts/collect_metrics.py --out results/metrics.json [--max-ccn 10] [--max-cognitive 16]
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile

SOURCES = ["api.py", "app.py", "auth.py", "dashboard.py", "db.py", "inventory.py", "movement.py",
           "queries.py", "reports.py", "resilience.py", "privacy"]
RUFF_RULES = "E,F,W,B,SIM"
BIN_DIR = os.path.dirname(sys.executable)   # інструменти з того ж оточення, не з довільного PATH


def safe_path(user_path):
    """Шлях лише всередині поточного каталогу проєкту (захист від path traversal)."""
    base = os.path.realpath(os.getcwd())
    path = os.path.realpath(os.path.join(base, user_path))
    if os.path.commonpath([base, path]) != base:
        raise SystemExit(f"Шлях поза каталогом проєкту: {user_path}")
    return path


def run(tool, *args):
    p = subprocess.run([os.path.join(BIN_DIR, tool), *args], capture_output=True, text=True)
    return p.stdout, p.stderr


def version(tool):
    return run(tool, "--version")[0].strip()


def lizard_metrics(m, errors):
    out, err = run("lizard", "-l", "python", "--csv", *SOURCES)
    rows = [r.split(",") for r in out.strip().splitlines() if r]
    if not rows:
        errors.append(f"lizard: {err.strip()[-200:]}")
        return
    ccn = [int(r[1]) for r in rows]
    m.update(functions=len(rows), nloc_functions=sum(int(r[0]) for r in rows),
             ccn_max=max(ccn), ccn_avg=round(sum(ccn) / len(ccn), 2))


def radon_json(kind, errors):
    """radon повертає помилки парсингу всередині JSON, а не кодом виходу."""
    out, _ = run("radon", kind, "-j", *SOURCES)
    data = json.loads(out or "{}")
    errors.extend(f"radon {kind} {f}: {v['error'][:120]}" for f, v in data.items() if "error" in v)
    return data


def radon_metrics(m, errors):
    raw = radon_json("raw", errors)
    m["sloc"] = sum(v.get("sloc", 0) for v in raw.values())
    # MI — відносна шкала, але розподіл по файлах скошений: беремо мінімум і медіану, не середнє
    mis = sorted(v["mi"] for v in radon_json("mi", errors).values() if "mi" in v)
    if mis:
        m.update(mi_min=round(mis[0], 2), mi_median=round(mis[len(mis) // 2], 2))


def cognitive_metrics(m, errors):
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "complexipy.json")
        out, err = run("complexipy", *SOURCES, "--output-format", "json", "--output", report, "-q")
        try:
            with open(report, encoding="utf-8") as fh:
                cx = [d["complexity"] for d in json.load(fh)]
            m.update(cognitive_max=max(cx), cognitive_total=sum(cx))
        except (OSError, ValueError, KeyError):
            errors.append(f"complexipy: {(err or out).strip()[-200:]}")


def ruff_metrics(m, errors):
    out, _ = run("ruff", "check", "--isolated", "--select", RUFF_RULES,
                 "--output-format", "json", *SOURCES)
    issues = json.loads(out or "[]")
    io_errors = [i for i in issues if i["code"] == "E902"]
    # ruff не зміг прочитати файл — це не «1 проблема», це зламаний вимір
    errors.extend(f"ruff E902 {i['filename']}" for i in io_errors)
    m["code_smells"] = len(issues) - len(io_errors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/metrics.json")
    ap.add_argument("--max-ccn", type=int, default=10)
    ap.add_argument("--max-cognitive", type=int, default=16)
    args = ap.parse_args()
    out_path = safe_path(args.out)

    errors, m = [], {}
    for collect in (lizard_metrics, radon_metrics, cognitive_metrics, ruff_metrics):
        collect(m, errors)

    result = {
        "env": {"python": platform.python_version(), "lizard": version("lizard"),
                "radon": version("radon"), "complexipy": version("complexipy"),
                "ruff": version("ruff"), "ruff_rules": RUFF_RULES},
        "metrics": m, "errors": errors,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if errors:
        print("\nMEASUREMENT ERROR: інструмент не зміг обробити файли — метрики недійсні", file=sys.stderr)
        return 2
    gate = m["ccn_max"] <= args.max_ccn and m["cognitive_max"] <= args.max_cognitive
    print(f"\nStatic gate: (CCN max {m['ccn_max']} <= {args.max_ccn}) AND "
          f"(Cognitive max {m['cognitive_max']} <= {args.max_cognitive}) -> {'PASS' if gate else 'FAIL'}")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
