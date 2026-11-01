"""Збирає статичні метрики одного файлу через CLI lizard / radon / complexipy / ruff.
Використання: python measure.py <file> -> JSON у stdout."""

import json
import os
import platform
import subprocess
import sys

f = sys.argv[1]
bindir = os.path.dirname(sys.executable)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


out = {"python": platform.python_version()}
# --- lizard
rc, so, se = run([f"{bindir}/lizard", "--version"])
out["lizard_ver"] = so.strip() or se.strip()
rc, so, se = run([f"{bindir}/lizard", "-l", "python", "--csv", f])
if rc in (0, 1) and so.strip():
    rows = [r.split(",") for r in so.strip().splitlines()]
    nloc = [int(r[0]) for r in rows]
    ccn = [int(r[1]) for r in rows]
    tok = [int(r[2]) for r in rows]
    out.update(
        lizard_funcs=len(rows),
        lizard_nloc_funcs=sum(nloc),
        lizard_ccn_sum=sum(ccn),
        lizard_ccn_max=max(ccn),
        lizard_tokens=sum(tok),
    )
else:
    out["lizard_error"] = (se or so).strip().splitlines()[-1:]
# --- radon
rc, so, se = run([f"{bindir}/radon", "--version"])
out["radon_ver"] = so.strip()
rc, so, se = run([f"{bindir}/radon", "raw", "-j", f])
try:
    raw = list(json.loads(so).values())[0]
    if "error" in raw:
        out["radon_raw_error"] = raw["error"][:120]
    else:
        out.update(
            radon_loc=raw["loc"],
            radon_lloc=raw["lloc"],
            radon_sloc=raw["sloc"],
            radon_comments=raw["comments"],
            radon_blank=raw["blank"],
        )
except Exception as e:
    out["radon_raw_error"] = (se or str(e))[-120:]
rc, so, se = run([f"{bindir}/radon", "cc", "-j", f])
try:
    blocks = list(json.loads(so).values())[0]
    if isinstance(blocks, dict) and "error" in blocks:
        out["radon_cc_error"] = blocks["error"][:120]
    else:
        cc = [b["complexity"] for b in blocks]
        out.update(radon_cc_blocks=len(cc), radon_cc_sum=sum(cc), radon_cc_max=max(cc))
except Exception as e:
    out["radon_cc_error"] = (se or str(e))[-120:]
rc, so, se = run([f"{bindir}/radon", "mi", "-j", "-s", f])
try:
    mi = list(json.loads(so).values())[0]
    if "error" in mi:
        out["radon_mi_error"] = mi["error"][:120]
    else:
        out.update(radon_mi=round(mi["mi"], 2), radon_mi_rank=mi["rank"])
except Exception as e:
    out["radon_mi_error"] = (se or str(e))[-120:]
# --- complexipy (когнітивна складність)
if os.path.exists(f"{bindir}/complexipy"):
    rc, so, se = run([f"{bindir}/complexipy", "--version"])
    out["complexipy_ver"] = (so or se).strip()
    import tempfile

    tmp = tempfile.mktemp(suffix=".json")
    rc, so, se = run(
        [f"{bindir}/complexipy", f, "--output-format", "json", "--output", tmp, "-q"]
    )
    try:
        data = json.load(open(tmp))
        cx = [d["complexity"] for d in data]
        out.update(cognitive_total=sum(cx), cognitive_max=max(cx))
    except Exception:
        out["cognitive_error"] = ((se or so).strip().splitlines() or ["?"])[-1][:120]
# --- ruff як джерело Code Smells (фіксований набір правил)
if os.path.exists(f"{bindir}/ruff"):
    rc, so, se = run([f"{bindir}/ruff", "--version"])
    out["ruff_ver"] = so.strip()
    rc, so, se = run(
        [
            f"{bindir}/ruff",
            "check",
            "--isolated",
            "--select",
            "E,F,W,C90,B,SIM",
            "--output-format",
            "json",
            f,
        ]
    )
    try:
        out["ruff_smells"] = len(json.loads(so))
    except Exception:
        out["ruff_smells"] = "ERR: " + (se.strip().splitlines() or ["?"])[-1][:100]
print(json.dumps(out, ensure_ascii=False))
