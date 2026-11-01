import glob
import json
import os
import sys

for d in sorted(glob.glob(sys.argv[1])):
    s = json.load(open(d + "/summary.json"))["metrics"]
    dur = s["http_req_duration"]
    f = s["http_req_failed"]
    r = s["http_reqs"]
    cpu = []
    rss = []
    load = []
    for line in open(d + "/resources.txt"):
        p = line.split()
        if p and p[0] == "LOAD":
            load.append(float(p[1]))
        elif len(p) == 2:
            cpu.append(float(p[0]))
            rss.append(int(p[1]) / 1024)
    ec = open(d + "/k6.txt").read().strip().splitlines()[-1].split()[-1]
    print(
        f"{os.path.basename(d):22s} avg={dur['avg']:.1f} med={dur['med']:.1f} p95={dur['p(95)']:.1f} p99={dur['p(99)']:.1f} max={dur['max']:.0f} fail={f['value']*100:.2f}% rps={r['rate']:.1f} reqs={r['count']} RSSmax={max(rss):.0f}MB loadmax={max(load)} k6exit={ec}"
    )
