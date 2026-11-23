"""ЛР7: синергетична матриця критичних зон (Hotspots) = складність коду × інтенсивність змін.

Складність файлу — з lizard (максимальна CC функції) і Холстеда (ефорт E, scripts/halstead_audit.py).
Мінливість — кількість комітів, що змінювали файл за останні N днів (git log).

  складність висока = CC_max > --cc-limit  АБО  E >= --effort-limit
  мінливість висока = комітів >= --churn-limit

  Hotspot  (червона) — висока складність + висока мінливість
  Sleeping (жовта)   — висока складність + низька мінливість
  Active   (зелена)  — низька складність + висока мінливість
  Stable   (сіра)    — низька складність + низька мінливість

Використання:
  python scripts/hotspots.py [--lizard-csv reports/lizard.csv] --json reports/hotspots.json \\
                             --markdown reports/hotspots.md
"""
import argparse
import csv
import datetime
import io
import json
import os
import subprocess
import sys
from collections import Counter

from halstead_audit import halstead, lex, python_files, safe_path

SOURCES = ["api.py", "app.py", "auth.py", "dashboard.py", "db.py", "inventory.py", "movement.py",
           "queries.py", "reports.py", "resilience.py", "privacy"]

# (складність висока, мінливість висока) -> категорія
CATEGORY = {
    (True, True): "Hotspot",
    (True, False): "Sleeping",
    (False, True): "Active",
    (False, False): "Stable",
}
ORDER = {"Hotspot": 0, "Sleeping": 1, "Active": 2, "Stable": 3}
ICON = {"Hotspot": "🔴", "Sleeping": "🟡", "Active": "🟢", "Stable": "⚪"}


def parse_args():
    ap = argparse.ArgumentParser(description="Hotspots: складність × мінливість")
    ap.add_argument("--lizard-csv", help="готовий звіт `lizard --csv`; без нього lizard запускається тут")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--cc-limit", type=int, default=10)
    ap.add_argument("--effort-limit", type=float, default=300_000)
    ap.add_argument("--churn-limit", type=int, default=4)
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    return ap.parse_args()


def lizard_rows(csv_path):
    if csv_path:
        with open(safe_path(csv_path), encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = subprocess.run([os.path.join(os.path.dirname(sys.executable), "lizard"),
                               "-l", "python", "--csv", *SOURCES],
                              capture_output=True, text=True, check=False).stdout
    # колонки lizard --csv: NLOC, CCN, token, PARAM, length, location, file, function, ...
    return [(os.path.normpath(r[6]), int(r[1])) for r in csv.reader(io.StringIO(text)) if r]


def churn(days):
    """Кількість комітів на файл за `days` днів; шляхи — відносно поточного каталогу."""
    prefix = subprocess.run(["git", "rev-parse", "--show-prefix"],
                            capture_output=True, text=True, check=True).stdout.strip()
    log = subprocess.run(["git", "-c", "core.quotepath=false", "log", f"--since={days}.days",
                          "--format=format:", "--name-only"],
                         capture_output=True, text=True, check=True).stdout
    names = (line[len(prefix):] for line in log.splitlines() if line.startswith(prefix) and line)
    return Counter(names)


def collect(args):
    cc_by_file = {}
    for path, ccn in lizard_rows(args.lizard_csv):
        cc_by_file.setdefault(path, []).append(ccn)
    commits = churn(args.days)
    base = os.path.realpath(os.getcwd())
    rows = []
    for path in python_files(SOURCES):
        rel = os.path.relpath(path, base)
        with open(path, encoding="utf-8") as fh:
            effort = halstead(*lex(fh.read()))["effort"]
        ccs = cc_by_file.get(rel, [0])
        rows.append(classify(args, {"file": rel, "functions": len(cc_by_file.get(rel, [])),
                                    "cc_max": max(ccs), "halstead_effort": effort,
                                    "commits": commits.get(rel, 0)}))
    rows.sort(key=lambda r: (ORDER[r["category"]], -r["halstead_effort"] * max(r["commits"], 1)))
    return rows


def classify(args, row):
    complex_ = row["cc_max"] > args.cc_limit or row["halstead_effort"] >= args.effort_limit
    volatile = row["commits"] >= args.churn_limit
    return {**row, "high_complexity": complex_, "high_churn": volatile,
            "category": CATEGORY[(complex_, volatile)]}


def _num(x):
    return f"{x:,.0f}".replace(",", " ")


def markdown(rows, args):
    lines = [f"### Hotspots: складність × мінливість (git log, {args.days} днів)", "",
             f"Пороги: CC_max > {args.cc_limit} або Halstead E ≥ {_num(args.effort_limit)}; "
             f"комітів ≥ {args.churn_limit}", "",
             "| Файл | CC max | Halstead E | Комітів | Категорія |", "|---|---|---|---|---|"]
    lines += [f"| `{r['file']}` | {r['cc_max']} | {_num(r['halstead_effort'])} | {r['commits']} | "
              f"{ICON[r['category']]} {r['category']} |" for r in rows]
    counts = Counter(r["category"] for r in rows)
    lines += ["", " · ".join(f"{ICON[c]} {c}: {counts.get(c, 0)}" for c in ORDER)]
    return "\n".join(lines)


def write(path, text):
    out = safe_path(path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    args = parse_args()
    rows = collect(args)
    report = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "params": {k: v for k, v in vars(args).items() if k not in ("json", "markdown")},
              "summary": dict(Counter(r["category"] for r in rows)), "files": rows}
    md = markdown(rows, args)
    print(md)
    if args.json:
        write(args.json, json.dumps(report, ensure_ascii=False, indent=2))
    if args.markdown:
        write(args.markdown, md + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
