"""ЛР5: вхідний фільтр перед збором метрик.

Перевіряє, що Python-файли мають однаковий «фізичний» формат: UTF-8 без BOM і LF.
Reliability Test показав, що інакше інструменти не помиляються голосно, а тихо
видають інші числа:
  * UTF-8 з BOM  -> radon cc/mi падає (U+FEFF), radon raw рахує LLOC/SLOC на 1 більше;
  * CP1251       -> radon і complexipy падають, а ruff показує 1 проблему замість 27
                    (E902 io-error), тобто «покращення» якості в 27 разів;
  * CRLF / змішані EOL на lizard/radon/complexipy/ruff не вплинули, але ламають diff-и
    і є передумовою до BOM/кодування з Windows-редакторів.

Використання: python scripts/check_text_hygiene.py [шляхи...]   (код виходу 1 = FAIL)
"""
import pathlib
import sys

EXCLUDE = {"__pycache__", ".venv", "venv", "mutants", "node_modules", ".git"}


def iter_files(paths):
    for p in map(pathlib.Path, paths or ["."]):
        if p.is_file():
            yield p
        else:
            for f in p.rglob("*.py"):
                if not EXCLUDE.intersection(f.parts):
                    yield f


def problems(path):
    data = path.read_bytes()
    found = []
    if data.startswith(b"\xef\xbb\xbf"):
        found.append("UTF-8 BOM")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        found.append(f"не UTF-8 (байт 0x{data[exc.start]:02x} на позиції {exc.start})")
    if b"\r\n" in data:
        found.append("CRLF")
    elif b"\r" in data:
        found.append("CR")
    return found


def main(argv):
    bad = 0
    for f in iter_files(argv):
        issues = problems(f)
        if issues:
            bad += 1
            print(f"FAIL {f}: {', '.join(issues)}")
    if bad:
        print(f"\n{bad} файл(ів) з невалідним форматом. Виправлення: "
              "git add --renormalize . (EOL) / зберегти як UTF-8 без BOM.")
        return 1
    print("OK: усі файли UTF-8 без BOM, LF")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
