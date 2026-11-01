"""ЛР5: відтворюваний збір статичних метрик (lizard / radon / complexipy / ruff).

Принципи (з висновків Reliability Test):
  1. Версії інструментів записуються в результат — число без версії сканера не порівнюється.
  2. Будь-яка помилка інструмента = FAIL збору (exit 2), а не «менше проблем».
     Інакше файл, який сканер не зміг прочитати, тихо випадає зі статистики.
  3. Набір правил ruff фіксований (--isolated), не залежить від локальних конфігів.

Використання:
  python scripts/collect_metrics.py --out results/metrics.json [--max-ccn 25] [--max-cognitive 30]
"""
import argparse
import json
import pathlib
import platform
import subprocess
import sys
import tempfile

SOURCES = ["api.py", "app.py", "auth.py", "dashboard.py", "db.py", "inventory.py",
           "queries.py", "reports.py", "resilience.py", "privacy"]
RUFF_RULES = "E,F,W,B,SIM"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def version(cmd):
    return run(cmd + ["--version"])[1].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/metrics.json")
    ap.add_argument("--max-ccn", type=int, default=25)
    ap.add_argument("--max-cognitive", type=int, default=30)
    args = ap.parse_args()
    errors, m = [], {}

    # --- lizard: NLOC, цикломатична складність
    rc, so, se = run(["lizard", "-l", "python", "--csv", *SOURCES])
    rows = [r.split(",") for r in so.strip().splitlines() if r]
    if not rows:
        errors.append(f"lizard: {se.strip()[-200:]}")
    else:
        ccn = [int(r[1]) for r in rows]
        m.update(functions=len(rows), nloc_functions=sum(int(r[0]) for r in rows),
                 ccn_max=max(ccn), ccn_avg=round(sum(ccn) / len(ccn), 2))

    # --- radon raw / mi: помилки парсингу radon повертає всередині JSON
    rc, so, se = run(["radon", "raw", "-j", *SOURCES])
    raw = json.loads(so or "{}")
    for f, v in raw.items():
        if "error" in v:
            errors.append(f"radon raw {f}: {v['error'][:120]}")
    m["sloc"] = sum(v.get("sloc", 0) for v in raw.values())
    rc, so, se = run(["radon", "mi", "-j", *SOURCES])
    mi = json.loads(so or "{}")
    for f, v in mi.items():
        if "error" in v:
            errors.append(f"radon mi {f}: {v['error'][:120]}")
    mis = [v["mi"] for v in mi.values() if "mi" in v]
    # MI — відносна шкала, але розподіл по файлах скошений: беремо мінімум і медіану, не середнє
    if mis:
        mis.sort()
        m.update(mi_min=round(mis[0], 2), mi_median=round(mis[len(mis) // 2], 2))

    # --- complexipy: когнітивна складність
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        pass
    rc, so, se = run(["complexipy", *SOURCES, "--output-format", "json", "--output", tmp.name, "-q"])
    try:
        cx = [d["complexity"] for d in json.load(open(tmp.name))]
        m.update(cognitive_max=max(cx), cognitive_total=sum(cx))
    except Exception:
        errors.append(f"complexipy: {(se or so).strip()[-200:]}")

    # --- ruff: code smells за фіксованим набором правил
    rc, so, se = run(["ruff", "check", "--isolated", "--select", RUFF_RULES,
                      "--output-format", "json", *SOURCES])
    issues = json.loads(so or "[]")
    io_errors = [i for i in issues if i["code"] == "E902"]
    if io_errors:  # ruff не зміг прочитати файл — це не «1 проблема», це зламаний вимір
        errors += [f"ruff E902 {i['filename']}" for i in io_errors]
    m["code_smells"] = len(issues) - len(io_errors)

    result = {
        "env": {"python": platform.python_version(), "lizard": version(["lizard"]),
                "radon": version(["radon"]), "complexipy": version(["complexipy"]),
                "ruff": version(["ruff"]), "ruff_rules": RUFF_RULES},
        "metrics": m, "errors": errors,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
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
