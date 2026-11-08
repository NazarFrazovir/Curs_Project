"""ЛР5, Reliability Test: метрики одного файлу через lizard / radon / complexipy / ruff.

Використання: python measure.py <файл у поточному каталозі> -> JSON у stdout.
Інструменти беруться з того ж віртуального оточення, що й інтерпретатор
(так порівнювалися різні версії Python та інструментів).
"""
import json
import os
import platform
import subprocess
import sys
import tempfile

BIN_DIR = os.path.dirname(sys.executable)


def safe_path(user_path):
    """Лише існуючий файл усередині поточного каталогу (захист від path traversal)."""
    base = os.path.realpath(os.getcwd())
    path = os.path.realpath(os.path.join(base, user_path))
    if os.path.commonpath([base, path]) != base or not os.path.isfile(path):
        raise SystemExit(f"Очікується файл усередині {base}: {user_path}")
    return path


def run(tool, *args):
    p = subprocess.run([os.path.join(BIN_DIR, tool), *args], capture_output=True, text=True)
    return p.stdout, p.stderr


def first_value(json_text):
    """radon -j повертає {шлях: дані} для одного файлу."""
    return next(iter(json.loads(json_text).values()))


def lizard(f, out):
    out["lizard_ver"] = run("lizard", "--version")[0].strip()
    so, se = run("lizard", "-l", "python", "--csv", "--", f)
    rows = [r.split(",") for r in so.strip().splitlines()]
    if not rows:
        out["lizard_error"] = se.strip()[-120:]
        return
    ccn = [int(r[1]) for r in rows]
    out.update(lizard_funcs=len(rows), lizard_nloc_funcs=sum(int(r[0]) for r in rows),
               lizard_ccn_sum=sum(ccn), lizard_ccn_max=max(ccn),
               lizard_tokens=sum(int(r[2]) for r in rows))


def radon(f, out):
    out["radon_ver"] = run("radon", "--version")[0].strip()
    fields = {
        "raw": lambda d: dict(radon_loc=d["loc"], radon_lloc=d["lloc"], radon_sloc=d["sloc"],
                              radon_comments=d["comments"], radon_blank=d["blank"]),
        "cc": lambda d: dict(radon_cc_blocks=len(d), radon_cc_sum=sum(b["complexity"] for b in d),
                             radon_cc_max=max(b["complexity"] for b in d)),
        "mi": lambda d: dict(radon_mi=round(d["mi"], 2), radon_mi_rank=d["rank"]),
    }
    for kind, extract in fields.items():
        args = [kind, "-j", "-s", "--", f] if kind == "mi" else [kind, "-j", "--", f]
        so, se = run("radon", *args)
        try:
            data = first_value(so)
        except (ValueError, StopIteration):
            out[f"radon_{kind}_error"] = se.strip()[-120:]
            continue
        if isinstance(data, dict) and "error" in data:
            out[f"radon_{kind}_error"] = data["error"][:120]
        else:
            out.update(extract(data))


def complexipy(f, out):
    out["complexipy_ver"] = run("complexipy", "--version")[0].strip()
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "cx.json")
        so, se = run("complexipy", f, "--output-format", "json", "--output", report, "-q")
        try:
            with open(report, encoding="utf-8") as fh:
                cx = [d["complexity"] for d in json.load(fh)]
            out.update(cognitive_total=sum(cx), cognitive_max=max(cx))
        except (OSError, ValueError, KeyError):
            out["cognitive_error"] = ((se or so).strip().splitlines() or ["?"])[-1][:120]


def ruff(f, out):
    out["ruff_ver"] = run("ruff", "--version")[0].strip()
    so, se = run("ruff", "check", "--isolated", "--select", "E,F,W,C90,B,SIM",
                 "--output-format", "json", "--", f)
    try:
        out["ruff_smells"] = len(json.loads(so))
    except ValueError:
        out["ruff_smells"] = "ERR: " + (se.strip().splitlines() or ["?"])[-1][:100]


def main():
    f = safe_path(sys.argv[1])
    out = {"python": platform.python_version()}
    for tool in (lizard, radon, complexipy, ruff):
        tool(f, out)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
