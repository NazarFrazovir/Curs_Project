"""ЛР10: аудит актуальності документації (Documentation Decay Audit) за історією Git.

Вхід — реєстр носіїв знань `docs/registry.json` (у корені репозиторію). Для кожного
документа-файлу знімає Git CLI метрики:

  * Last Updated Age      git log -1 --format=%cs -- <doc>               -> днів від дати аудиту
  * Code-Doc Change Ratio git log --oneline -- <код>  vs  -- <doc>        -> комітів коду / документа
  * Code behind doc       git log --oneline <ост.коміт doc>..HEAD -- <код> -> змін коду ПІСЛЯ оновлення doc
  * Access evidence       кількість файлів репозиторію, що посилаються на документ (+ ручна примітка)

і перевіряє структурний дрейф архітектурного паспорта (structure drift):

  * кожен HTTP-маршрут коду згадано в docs/sdd.md, кожен /api/* маршрут — у README;
  * кожну таблицю/представлення з sql/*.sql згадано в docs/sdd.md;
  * кожен сервіс docker-compose.yml і кожну змінну оточення згадано в docs/isd.md.

Запуск (з будь-якої теки репозиторію):
  python scripts/doc_audit.py                    # таблиця метрик + дрейф
  python scripts/doc_audit.py --today 2026-11-23 # фіксована дата аудиту (відтворюваність)
  python scripts/doc_audit.py --gate             # exit 1, якщо паспорт неактуальний
  python scripts/doc_audit.py --md out.md        # звіт у Markdown
"""
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SUSPICIOUS_DAYS = 90
STALE_DAYS = 180
DRIFT_COMMITS = 20
APP = "last – копія"

BLUEPRINT_RE = re.compile(r"""(\w+)\s*=\s*Blueprint\(\s*['"](\w+)['"][^)]*?(?:url_prefix\s*=\s*['"]([^'"]*)['"])?\s*\)""")
ROUTE_RE = re.compile(r"""@(\w+)\.(get|post|put|patch|delete|route)\(\s*['"]([^'"]+)['"]""")
RULE_RE = re.compile(r"""add_url_rule\(\s*['"]([^'"]+)['"]""")
TABLE_RE = re.compile(r"CREATE\s+(?:TABLE|(?:OR\s+REPLACE\s+)?VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)", re.I)
ENV_CODE_RE = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*['"]([A-Z][A-Z0-9_]+)['"]""")
ENV_COMPOSE_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]+)\}|^\s{6}([A-Z][A-Z0-9_]+):", re.M)


# ---------- git ----------

def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def repo_root(start):
    return Path(git(start, "rev-parse", "--show-toplevel"))


def count_commits(root, paths, since=None):
    if not paths:
        return 0
    rev = [f"{since}..HEAD"] if since else []
    out = git(root, "log", "--oneline", *rev, "--", *paths)
    return len(out.splitlines()) if out else 0


def last_commit(root, path):
    out = git(root, "log", "-1", "--format=%H %cs", "--", path)
    return tuple(out.split()) if out else (None, None)


def grep_files(root, needle, scope):
    out = subprocess.run(["git", "-C", str(root), "grep", "-l", "-F", needle, "--", scope],
                         capture_output=True, text=True)
    return {line for line in out.stdout.splitlines() if line}


def inbound_refs(root, path):
    """Скільки tracked-файлів посилаються на документ (доказ споживання).

    Шукаємо шлях від кореня репозиторію; для файлів застосунку — ще й шлях від теки
    застосунку, але лише всередині неї; файл у корені — лише серед файлів кореня.
    """
    if "/" not in path:
        files = grep_files(root, path, ":(glob)*")
    else:
        files = grep_files(root, path, ".")
        if path.startswith(APP + "/"):
            files |= grep_files(root, path[len(APP) + 1:], APP)
    files.discard(path)
    return len(files)


# ---------- метрики документа ----------

@dataclass
class DocMetrics:
    entry: dict
    last_updated: str = None
    age_days: int = None
    doc_commits: int = 0
    code_commits: int = 0
    code_behind: int = 0
    refs: int = 0
    flags: list = field(default_factory=list)


def measure(root, entry, today):
    m = DocMetrics(entry)
    path, covers = entry.get("path"), entry.get("covers", [])
    if not path or not (root / path).exists():
        m.flags.append("не файл / немає в репозиторії")
        return m
    sha, day = last_commit(root, path)
    if sha is None:
        m.flags.append("не закомічено")
        return m
    m.last_updated = day
    m.age_days = (today - date.fromisoformat(day)).days
    m.doc_commits = count_commits(root, [path])
    m.code_commits = count_commits(root, covers)
    m.code_behind = count_commits(root, covers, since=sha)
    m.refs = inbound_refs(root, path)
    m.flags = classify(m)
    return m


def classify(m):
    entry, flags = m.entry, []
    review = entry.get("review_days")
    if m.age_days > STALE_DAYS:
        flags.append("ймовірно застарілий (>180 дн.)")
    elif m.age_days > SUSPICIOUS_DAYS:
        flags.append("підозрілий (>90 дн.)")
    if review and m.age_days > review:
        flags.append(f"прострочено перегляд ({review} дн.)")
    if m.code_behind > DRIFT_COMMITS:
        flags.append(f"структурний дрейф: {m.code_behind} змін коду без оновлення")
    elif m.code_behind and entry.get("kind") == "product":
        flags.append(f"відстає від коду на {m.code_behind} коміт(и)")
    if m.refs == 0 and not entry.get("consumer"):
        flags.append("без споживача (Dead Documentation?)")
    return flags


# ---------- структурний дрейф паспорта ----------

def app_sources(root):
    base = root / APP
    skip = ("tests", "scripts", "experiments", "load")
    return [p for p in sorted(base.rglob("*.py"))
            if not any(part in skip for part in p.relative_to(base).parts)]


def routes_in(text):
    prefixes = {var: prefix or "" for var, _, prefix in BLUEPRINT_RE.findall(text)}
    found = [(method.upper(), prefixes.get(var, "") + path)
             for var, method, path in ROUTE_RE.findall(text) if var in prefixes]
    found += [("GET", path) for path in RULE_RE.findall(text)]
    return found


def code_routes(root):
    routes = []
    for source in app_sources(root):
        routes += routes_in(source.read_text(encoding="utf-8"))
    return sorted(set(routes), key=lambda r: (r[1], r[0]))


def sql_objects(root):
    names = set()
    for sql in sorted((root / APP / "sql").glob("*.sql")):
        names.update(n.split(".")[-1] for n in TABLE_RE.findall(sql.read_text(encoding="utf-8")))
    return sorted(names)


def compose_services(text):
    block = text.split("\nservices:", 1)[-1].split("\nvolumes:", 1)[0]
    return re.findall(r"^  ([\w-]+):\s*$", block, re.M)


def env_vars(root):
    names = set()
    for source in app_sources(root):
        names.update(ENV_CODE_RE.findall(source.read_text(encoding="utf-8")))
    compose = (root / APP / "docker-compose.yml").read_text(encoding="utf-8")
    for a, b in ENV_COMPOSE_RE.findall(compose):
        names.add(a or b)
    return sorted(names)


def missing(items, doc_path):
    if not doc_path.exists():
        return list(items)
    text = doc_path.read_text(encoding="utf-8")
    return [item for item in items if item not in text]


def drift(root):
    routes = code_routes(root)
    compose = (root / APP / "docker-compose.yml").read_text(encoding="utf-8")
    return {
        "SDD: маршрути без опису": missing([p for _, p in routes], root / "docs/sdd.md"),
        "SDD: таблиці без опису": missing(sql_objects(root), root / "docs/sdd.md"),
        "README: публічні /api маршрути без опису": missing(
            [p for _, p in routes if p.startswith("/api/")], root / APP / "README.md"),
        "ISD: сервіси compose без опису": missing(compose_services(compose), root / "docs/isd.md"),
        "ISD: змінні оточення без опису": missing(env_vars(root), root / "docs/isd.md"),
    }


# ---------- вихід ----------

def table(metrics):
    yield ("| Документ | Тип | Оновлено | Вік, дн. | Комітів doc | Комітів коду | Код після doc "
           "| Посилань | Сигнали |")
    yield "|---|---|---|---:|---:|---:|---:|---:|---|"
    for m in metrics:
        e = m.entry
        yield (f"| `{e.get('path') or e.get('location')}` | {e['kind']} | {m.last_updated or '—'} | "
               f"{'' if m.age_days is None else m.age_days} | {m.doc_commits} | {m.code_commits} | "
               f"{m.code_behind} | {m.refs} | {'; '.join(m.flags) or 'OK'} |")


def drift_lines(found):
    for name, items in found.items():
        status = "OK" if not items else f"**{len(items)}**: " + ", ".join(f"`{i}`" for i in items[:12])
        if len(items) > 12:
            status += f" … (+{len(items) - 12})"
        yield f"- {name}: {status}"


# Вік понад 90/180 днів — сигнал для людини; ворота блокують лише порушення регламенту.
INFORMATIONAL = ("без споживача", "підозрілий", "ймовірно застарілий")


def gate_failures(metrics, found):
    failures = []
    for m in (m for m in metrics if m.entry.get("passport")):
        blocking = [f for f in m.flags if not f.startswith(INFORMATIONAL)]
        if blocking:
            failures.append(f"{m.entry['path']}: {', '.join(blocking)}")
    failures += [f"{name}: {len(items)}" for name, items in found.items() if items]
    return failures


def render(metrics, found, today):
    lines = [f"# Documentation Currency Audit — {today.isoformat()}", "", *table(metrics), "",
             "## Структурний дрейф паспорта", "", *drift_lines(found), ""]
    failures = gate_failures(metrics, found)
    verdict = "PASS — паспорт актуальний" if not failures else "FAIL — Documentation Decay"
    lines += [f"## Вердикт: **{verdict}**", "", *(f"- {f}" for f in failures)]
    return "\n".join(lines) + "\n", not failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Аудит актуальності документації за Git")
    parser.add_argument("--registry", help="шлях до registry.json (типово docs/registry.json)")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--md", help="зберегти звіт у Markdown")
    parser.add_argument("--gate", action="store_true", help="exit 1 при неактуальному паспорті")
    args = parser.parse_args(argv)
    root = repo_root(Path.cwd())
    registry = json.loads(Path(args.registry or root / "docs/registry.json").read_text(encoding="utf-8"))
    metrics = [measure(root, entry, args.today) for entry in registry["documents"]]
    report, ok = render(metrics, drift(root), args.today)
    if args.md:
        Path(args.md).write_text(report, encoding="utf-8")
    print(report)
    return 0 if ok or not args.gate else 1


if __name__ == "__main__":
    sys.exit(main())
