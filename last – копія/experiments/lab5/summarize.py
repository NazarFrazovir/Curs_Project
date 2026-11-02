"""ЛР5, Stability Test: зведення прогонів k6 (summary.json + resources.txt + k6.txt).

Використання: python summarize.py 'expS/[A-E]_*'   (шаблон відносно поточного каталогу)
"""
import glob
import json
import os
import sys


def run_dirs(pattern):
    """Лише каталоги всередині поточного (захист від path traversal через шаблон)."""
    base = os.path.realpath(os.getcwd())
    for d in sorted(glob.glob(pattern)):
        path = os.path.realpath(d)
        if os.path.commonpath([base, path]) == base and os.path.isdir(path):
            yield path


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def summarize(d):
    s = json.loads(read(os.path.join(d, "summary.json")))["metrics"]
    dur, failed, reqs = s["http_req_duration"], s["http_req_failed"], s["http_reqs"]
    rss, load = [], []
    for line in read(os.path.join(d, "resources.txt")).splitlines():
        p = line.split()
        if p and p[0] == "LOAD":
            load.append(float(p[1]))
        elif len(p) == 2:
            rss.append(int(p[1]) / 1024)
    exit_code = read(os.path.join(d, "k6.txt")).strip().splitlines()[-1].split()[-1]
    return (f"{os.path.basename(d):22s} avg={dur['avg']:.1f} med={dur['med']:.1f} "
            f"p95={dur['p(95)']:.1f} p99={dur['p(99)']:.1f} max={dur['max']:.0f} "
            f"fail={failed['value'] * 100:.2f}% rps={reqs['rate']:.1f} reqs={reqs['count']} "
            f"RSSmax={max(rss, default=0):.0f}MB loadmax={max(load, default=0)} k6exit={exit_code}")


if __name__ == "__main__":
    for run_dir in run_dirs(sys.argv[1]):
        print(summarize(run_dir))
