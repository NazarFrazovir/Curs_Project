"""ЛР6: лексичний аудит за Холстедом (CLI).

Оператори і операнди визначаються так, як у методичці:
  * оператори (η1, N1) — ключові слова Python (if, for, def, return, and, in, ...),
    знаки операцій і роздільники: + - * / == = ( ) [ ] { } , : . -> @ ...
  * операнди (η2, N2) — імена (змінні, функції, модулі, атрибути), числа, константи
    True / False / None (у Python це ключові слова, але за Холстедом — значення, тобто операнди),
    рядкові літерали (весь літерал — один операнд, включно з f-рядком і SQL-текстом).
  Коментарі та docstring-и не враховуються: це документація, а не логіка.

Похідні метрики:
  η = η1 + η2           N = N1 + N2
  V = N · log2(η)       D = (η1 / 2) · (N2 / η2)       E = V · D
  B = V / 3000 (оцінка кількості дефектів), T = E / 18 c (час на написання)

Чому власний сканер, а не лише `radon hal`: radon рахує операторами тільки
арифметику, порівняння і булеві операції (if/for/виклики/дужки ігноруються),
тому для api.py дає η1 = 2. Результати radon наводяться для порівняння (--radon).

Використання:
  python scripts/halstead_audit.py                    # глобальна базова лінія + усі файли
  python scripts/halstead_audit.py inventory.py db.py # лише вказані файли
  python scripts/halstead_audit.py --json results/halstead.json
"""
import argparse
import ast
import io
import json
import keyword
import math
import os
import sys
import tokenize

DEFAULT_SOURCES = ["api.py", "app.py", "auth.py", "dashboard.py", "db.py", "inventory.py", "movement.py",
                   "queries.py", "reports.py", "resilience.py", "privacy"]
FSTRING_START = getattr(tokenize, "FSTRING_START", None)   # Python 3.12+
FSTRING_END = getattr(tokenize, "FSTRING_END", None)
CONSTANT_WORDS = {"True", "False", "None"}   # ключові слова-значення -> операнди


def safe_path(user_path):
    base = os.path.realpath(os.getcwd())
    path = os.path.realpath(os.path.join(base, user_path))
    if os.path.commonpath([base, path]) != base:
        raise SystemExit(f"Шлях поза каталогом проєкту: {user_path}")
    return path


def python_files(paths):
    for p in paths:
        p = safe_path(p)
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d != "__pycache__")
                yield from (os.path.join(root, f) for f in sorted(files) if f.endswith(".py"))
        else:
            yield p


def docstring_starts(source):
    """Позиції (рядок, колонка) docstring-ів модуля, класів і функцій."""
    starts = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                starts.add((body[0].lineno, body[0].col_offset))
    return starts


OPERATOR, OPERAND = "operator", "operand"
# роль токена за його типом; NAME вирішується окремо (ключове слово чи ідентифікатор)
KIND_BY_TYPE = {tokenize.OP: OPERATOR, tokenize.NUMBER: OPERAND, tokenize.STRING: OPERAND}


def merge_fstrings(tokens):
    """У Python 3.12+ f-рядок розбивається на частини — збираємо його назад в один STRING,
    щоб результат не залежав від версії інтерпретатора (урок ЛР5)."""
    depth, parts, start = 0, [], None
    for tok in tokens:
        if tok.type == FSTRING_START:
            depth += 1
            start = start or tok.start
        if not depth:
            yield tok
            continue
        parts.append(tok.string)
        depth -= tok.type == FSTRING_END
        if not depth:
            yield tokenize.TokenInfo(tokenize.STRING, "".join(parts), start, tok.end, tok.line)
            parts, start = [], None


def token_kind(tok, docs):
    if tok.type == tokenize.NAME:
        is_operator = keyword.iskeyword(tok.string) and tok.string not in CONSTANT_WORDS
        return OPERATOR if is_operator else OPERAND
    if tok.start in docs:
        return None  # docstring — документація, не логіка
    return KIND_BY_TYPE.get(tok.type)  # коментарі, відступи, переводи рядків -> None


def lex(source):
    """Повертає (оператори, операнди) — списки токенів у порядку появи."""
    docs = docstring_starts(source)
    found = {OPERATOR: [], OPERAND: [], None: []}
    for tok in merge_fstrings(tokenize.generate_tokens(io.StringIO(source).readline)):
        found[token_kind(tok, docs)].append(tok.string)
    return found[OPERATOR], found[OPERAND]


def halstead(operators, operands):
    n1, n2 = len(set(operators)), len(set(operands))
    N1, N2 = len(operators), len(operands)
    vocab, length = n1 + n2, N1 + N2
    volume = length * math.log2(vocab) if vocab > 1 else 0.0
    difficulty = (n1 / 2) * (N2 / n2) if n2 else 0.0
    effort = volume * difficulty
    return {"n1": n1, "n2": n2, "N1": N1, "N2": N2, "vocabulary": vocab, "length": length,
            "volume": round(volume, 2), "difficulty": round(difficulty, 2),
            "effort": round(effort, 1), "bugs": round(volume / 3000, 3),
            "time_h": round(effort / 18 / 3600, 2)}


def sloc(source):
    """SLOC за radon raw (той самий інструмент, що й у ЛР5): рядки коду без коментарів і порожніх."""
    from radon.raw import analyze
    return analyze(source).sloc


def radon_total(source):
    from radon.metrics import h_visit
    t = h_visit(source).total
    return {"n1": t.h1, "n2": t.h2, "N1": t.N1, "N2": t.N2,
            "volume": round(t.volume, 2), "difficulty": round(t.difficulty, 2),
            "effort": round(t.effort, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=DEFAULT_SOURCES)
    ap.add_argument("--json", help="зберегти результат у JSON")
    ap.add_argument("--radon", action="store_true", help="додати колонки radon hal для порівняння")
    args = ap.parse_args()

    base = os.path.realpath(os.getcwd())
    all_ops, all_opnds, rows = [], [], []
    for path in python_files(args.paths):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        ops, opnds = lex(src)
        all_ops += ops
        all_opnds += opnds
        row = {"file": os.path.relpath(path, base), "sloc": sloc(src), **halstead(ops, opnds)}
        if args.radon:
            row["radon"] = radon_total(src)
        rows.append(row)

    rows.sort(key=lambda r: r["effort"], reverse=True)
    glob = halstead(all_ops, all_opnds)

    print("GLOBAL BASELINE (увесь проєкт, словник = об'єднання токенів усіх файлів)")
    print(f"  файлів: {len(rows)}   SLOC: {sum(r['sloc'] for r in rows)}")
    print(f"  η1 (унікальні оператори) = {glob['n1']}    η2 (унікальні операнди) = {glob['n2']}")
    print(f"  N1 (усі оператори)       = {glob['N1']}   N2 (усі операнди)       = {glob['N2']}")
    print(f"  η = {glob['vocabulary']}   N = {glob['length']}   V = {glob['volume']}   "
          f"D = {glob['difficulty']}   E = {glob['effort']}")
    print()
    head = f"{'#':>2} {'файл':28} {'SLOC':>5} {'η1':>4} {'η2':>5} {'N1':>6} {'N2':>6} " \
           f"{'V':>9} {'D':>7} {'E':>12} {'B':>6}"
    print(head)
    print("-" * len(head))
    for i, r in enumerate(rows, 1):
        print(f"{i:>2} {r['file']:28} {r['sloc']:>5} {r['n1']:>4} {r['n2']:>5} {r['N1']:>6} "
              f"{r['N2']:>6} {r['volume']:>9.1f} {r['difficulty']:>7.2f} {r['effort']:>12.1f} "
              f"{r['bugs']:>6.2f}")
        if args.radon:
            rd = r["radon"]
            print(f"   {'  radon hal:':28} {'':>5} {rd['n1']:>4} {rd['n2']:>5} {rd['N1']:>6} "
                  f"{rd['N2']:>6} {rd['volume']:>9.1f} {rd['difficulty']:>7.2f} {rd['effort']:>12.1f}")

    if args.json:
        out = safe_path(args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"global": glob, "files": rows}, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
