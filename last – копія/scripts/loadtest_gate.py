"""ЛР5: стійкий до шуму Quality Gate для навантажувального тесту.

Один прогін k6 — це одна вибірка, а не факт. Stability Test показав, що той самий код
дає p95 від ~70 до ~480 мс залежно від сусідніх процесів і квоти CPU. Тому:
  * запускаємо N >= 3 прогонів і беремо МЕДІАНУ p95 (медіана стійка до одиночного викиду);
  * рахуємо розкид (max - min) / median; якщо він великий — середовище нестабільне,
    результат INVALID (перезапуск на чистому раннері), а не FAIL коду;
  * якщо під час прогону контейнер застосунку тротлився по CPU (cpu.stat nr_throttled > 0),
    вимір відображає ліміт інфраструктури, а не код -> INVALID;
  * error rate — частка (відносна шкала), агрегуємо як сумарні помилки / сумарні запити.

Використання:
  python scripts/loadtest_gate.py results/k6_ci_*.json --slo-p95 300 --max-error-rate 0.01 --max-spread 0.5 \
         --throttled-periods $(приріст nr_throttled з cpu.stat контейнера web)
Код виходу: 0 PASS, 1 FAIL, 3 INVALID (шум середовища).
"""
import argparse
import json
import os
import statistics
import sys


def safe_path(user_path):
    """Шлях лише всередині поточного каталогу проєкту (захист від path traversal)."""
    base = os.path.realpath(os.getcwd())
    path = os.path.realpath(os.path.join(base, user_path))
    if os.path.commonpath([base, path]) != base:
        raise SystemExit(f"Шлях поза каталогом проєкту: {user_path}")
    return path


def read_json(user_path):
    with open(safe_path(user_path), encoding="utf-8") as fh:
        return json.load(fh)


def load(path):
    m = read_json(path)["metrics"]
    return {
        "p95": m["http_req_duration"]["p(95)"],
        "reqs": m["http_reqs"]["count"],
        "failed": m["http_req_failed"]["value"] * m["http_reqs"]["count"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("summaries", nargs="+")
    ap.add_argument("--slo-p95", type=float, default=300.0)
    ap.add_argument("--max-error-rate", type=float, default=0.01)
    ap.add_argument("--max-spread", type=float, default=0.5)
    ap.add_argument("--throttled-periods", type=int, default=0,
                    help="приріст nr_throttled контейнера web за час тесту")
    a = ap.parse_args()

    runs = [load(p) for p in a.summaries]
    p95s = [r["p95"] for r in runs]
    med = statistics.median(p95s)
    spread = (max(p95s) - min(p95s)) / med if med else 0.0
    err = sum(r["failed"] for r in runs) / sum(r["reqs"] for r in runs)

    print("p95 по прогонах, мс:", ", ".join(f"{x:.1f}" for x in p95s))
    print(f"median p95 = {med:.1f} мс | spread = {spread:.0%} | error rate = {err:.3%}")

    if len(runs) < 3:
        print("INVALID: потрібно щонайменше 3 прогони")
        return 3
    if a.throttled_periods > 0:
        print(f"INVALID: контейнер застосунку тротлився {a.throttled_periods} періодів CFS — "
              "результат визначає ліміт --cpus, а не код")
        return 3
    if spread > a.max_spread:
        print(f"INVALID: розкид {spread:.0%} > {a.max_spread:.0%} — середовище зашумлене, "
              "перезапустіть на ізольованому раннері")
        return 3
    ok = med < a.slo_p95 and err < a.max_error_rate
    print(f"Gate: (median p95 {med:.1f} < {a.slo_p95:.0f}) AND (errors {err:.3%} < "
          f"{a.max_error_rate:.0%}) -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
