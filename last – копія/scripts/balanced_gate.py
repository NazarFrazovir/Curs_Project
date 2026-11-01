"""ЛР5: збалансований Quality Gate «покриття + мутаційний аналіз» (захист від Закону Гудхарта).

    PASS  <=>  (Line Coverage >= 80 %) AND (Mutation Score >= 65 %)

Coverage показує, що рядок ВИКОНАВСЯ під час тестів; Mutation Score — що тести
ПОМІТИЛИ б, якби в цьому рядку була помилка. Тест без assert піднімає першу
метрику, але не другу, тому накрутити обидві одночасно можна лише справжніми тестами.

Mutation Score (як у Stryker):
    (killed + timeout) / (killed + timeout + survived + no_tests)
Мутанти skipped / suspicious не входять у знаменник.

Використання:
  python scripts/balanced_gate.py --coverage results/coverage.json \
         --mutation mutants/mutmut-cicd-stats.json --min-coverage 80 --min-mutation 65
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", required=True, help="вихід `coverage json`")
    ap.add_argument("--mutation", required=True, help="вихід `mutmut export-cicd-stats`")
    ap.add_argument("--min-coverage", type=float, default=80.0)
    ap.add_argument("--min-mutation", type=float, default=65.0)
    a = ap.parse_args()

    cov = json.load(open(a.coverage, encoding="utf-8"))["totals"]
    line_cov = 100.0 * cov["covered_lines"] / cov["num_statements"] if cov["num_statements"] else 0.0

    s = json.load(open(a.mutation, encoding="utf-8"))
    detected = s["killed"] + s["timeout"]
    undetected = s["survived"] + s["no_tests"]
    mut = 100.0 * detected / (detected + undetected) if detected + undetected else 0.0

    c_ok, m_ok = line_cov >= a.min_coverage, mut >= a.min_mutation
    print(f"Line Coverage  = {line_cov:5.1f} %  (поріг {a.min_coverage:.0f} %)  {'OK' if c_ok else 'FAIL'}")
    print(f"Mutation Score = {mut:5.1f} %  (поріг {a.min_mutation:.0f} %)  {'OK' if m_ok else 'FAIL'}"
          f"   [killed={s['killed']} timeout={s['timeout']} survived={s['survived']} no_tests={s['no_tests']}]")
    if c_ok and not m_ok:
        print("УВАГА: високе покриття при низькому Mutation Score — ознака тестів без перевірок (Goodhart)")
    verdict = c_ok and m_ok
    print("Balanced Quality Gate:", "PASS" if verdict else "FAIL")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
