"""ЛР8: об'єктні метрики CK (Чидамбер-Кемерер) і MOOD (Абреу) для Python-коду проєкту.

Навіщо власний аналізатор: SonarQube/SonarCloud більше не рахує CK-метрики —
lcom4 застаріла ще у SonarQube 4.1, class_complexity видалено, метрику зачеплення
класів прибрано; запит до api/measures/component з цими ключами повертає помилку
«metric keys are not found». Тому CK/MOOD рахуються тут, а результат віддається
у тому ж форматі, що й SonarQube Web API (component -> measures[metric, value]).

Одиниця аналізу:
  * клас (ClassDef) — методи, атрибути self.*, поля dataclass;
  * модуль без класів (Flask-блюпринти) — функції модуля як «методи»,
    змінні модуля як «атрибути». Для Python це природна одиниця інкапсуляції.

CK:
  WMC  = сума цикломатичної складності методів (radon)
  CBO  = кількість різних компонентів, з якими одиниця зв'язана в обидва боки:
         імпортовані символи/модулі, яких вона торкається, + класи проєкту, що торкаються її
  RFC  = методи + різні виклики з них
  LCOM4 = кількість зв'язних компонент графа методів (ребро: спільний атрибут або виклик)
  LCOM-HS = (середнє μ(a) − m) / (1 − m), Henderson-Sellers, 0 — ідеал, 1 — нуль згуртованості
  DIT  = len(MRO) − 1 (клас без явного предка = 1), NOC — кількість прямих нащадків у проєкті
  PIM  = публічні методи (власні + успадковані від предків проєкту), Overridden — перевизначені

MOOD (по всіх класах проєкту):
  MHF, AHF — частка прихованих (з «_») методів/атрибутів
  MIF, AIF — частка успадкованих методів/атрибутів серед доступних
  COF = зв'язки клієнт-постачальник між класами / (TC² − TC)
  PF  = перевизначення / Σ(нові методи × кількість нащадків)

Використання:
  python scripts/oo_metrics.py                         # таблиця CK + MOOD
  python scripts/oo_metrics.py --json artifacts/oo.json
  python scripts/oo_metrics.py --unit warehouse_service.py:WarehouseService --graph
"""
import argparse
import ast
import builtins
import importlib
import json
import os
import sys
from collections import defaultdict

from radon.complexity import cc_visit

from halstead_audit import python_files, safe_path

# увесь код застосунку: модулі в корені (крім скрипта ініціалізації БД) + пакет privacy
SOURCES = sorted(f for f in os.listdir(".") if f.endswith(".py") and f != "setup_db.py") + ["privacy"]
BUILTINS = set(dir(builtins)) | {"self", "cls"}
CONSTRUCTORS = {"__init__", "__post_init__", "__new__"}


# ---------------------------------------------------------------- розбір файлів

def import_table(tree):
    """Ім'я в коді -> компонент, з яким воно зв'язує (модуль або модуль.символ)."""
    table = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            table.update({(a.asname or a.name).split(".")[0]: a.name for a in node.names})
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            table.update({a.asname or a.name: f"{prefix}.{a.name}".lstrip(".") for a in node.names})
    return table


def referenced_names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def called_names(node):
    calls = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            calls.add(ast.unparse(n.func))
    return calls


def self_attributes(func):
    return {n.attr for n in ast.walk(func)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"}


def assigned_names(statements):
    """Імена, яким присвоюють значення на цьому рівні (константи модуля, поля класу)."""
    targets = []
    for n in statements:
        if isinstance(n, ast.Assign):
            targets += n.targets
        elif isinstance(n, ast.AnnAssign):
            targets.append(n.target)
    return {t.id for t in targets if isinstance(t, ast.Name)}


def functions_of(statements):
    return [n for n in statements if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def class_fields(cls):
    """Атрибути класу: присвоєння в тілі класу (у т.ч. поля dataclass) і self.* у методах."""
    methods = functions_of(cls.body)
    names = {m.name for m in methods}
    fields = assigned_names(cls.body)
    for m in methods:
        fields |= self_attributes(m) - names
    return fields


# ---------------------------------------------------------------- одиниці аналізу

def class_unit(path, cls, imports):
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    method_names = {m.name for m in methods}
    access = {m.name: self_attributes(m) for m in methods}
    return {"kind": "class", "file": path, "name": cls.name, "node": cls, "imports": imports,
            "methods": methods, "fields": class_fields(cls),
            "access": {k: v - method_names for k, v in access.items()},
            "self_calls": {k: v & method_names for k, v in access.items()},
            "bases": [ast.unparse(b) for b in cls.bases]}


def module_unit(path, tree, imports):
    funcs = functions_of(tree.body)
    if not funcs:
        return None
    func_names = {f.name for f in funcs}
    fields = assigned_names(tree.body)
    used = {f.name: referenced_names(f) for f in funcs}
    return {"kind": "module", "file": path, "name": "<module>", "node": tree, "imports": imports,
            "methods": funcs, "fields": fields,
            "access": {k: v & fields for k, v in used.items()},
            "self_calls": {k: v & func_names - {k} for k, v in used.items()}, "bases": []}


def load_units(paths):
    base = os.path.realpath(os.getcwd())
    units = []
    for path in python_files(paths):
        rel = os.path.relpath(path, base)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        imports = import_table(tree)
        cc = {f.fullname: f.complexity for f in cc_visit(source) if hasattr(f, "fullname")}
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        for unit in [class_unit(rel, c, imports) for c in classes] + [module_unit(rel, tree, imports)]:
            if unit:
                unit["cc"] = cc
                units.append(unit)
    return units


# ---------------------------------------------------------------- CK

def wmc(unit):
    prefix = "" if unit["kind"] == "module" else unit["name"] + "."
    return sum(unit["cc"].get(prefix + m.name, 1) for m in unit["methods"])


def unit_body(unit):
    if unit["kind"] == "class":
        return [unit["node"]]
    return [n for n in unit["node"].body if not isinstance(n, ast.ClassDef)]


def efferent(unit, class_index):
    """Компоненти, якими користується одиниця: імпортовані символи + класи проєкту."""
    names = set().union(*map(referenced_names, unit_body(unit))) - BUILTINS
    imported = {unit["imports"][n] for n in names & unit["imports"].keys()}
    local = names & class_index.keys() - unit["imports"].keys() - {unit["name"]}
    return imported | {f"{class_index[n]}:{n}" for n in local}


def unit_id(unit):
    return f"{unit['file']}:{unit['name']}"


def symbol_targets(unit):
    """Під якими іменами одиницю можуть імпортувати інші: модуль.Клас або модуль."""
    module = unit["file"][:-3].replace(os.sep, ".")
    return {f"{module}.{unit['name']}", unit["name"]} if unit["kind"] == "class" else {module}


def afferent(unit, units, eff):
    targets = symbol_targets(unit)
    own = unit_id(unit)
    users = set()
    for other in units:
        if unit_id(other) == own:
            continue
        hits = {c.split(":")[-1] for c in eff[unit_id(other)]} | {c.split(".")[0] for c in eff[unit_id(other)]}
        if targets & ({c for c in eff[unit_id(other)]} | hits):
            users.add("<-" + unit_id(other))
    return users


def _linked(unit, a, b):
    return bool(unit["access"][a] & unit["access"][b]) or b in unit["self_calls"][a] \
        or a in unit["self_calls"][b]


def _components(nodes, edges):
    """Кількість зв'язних компонент графа (обхід у ширину)."""
    seen, count = set(), 0
    for start in nodes:
        if start in seen:
            continue
        count += 1
        queue = [start]
        while queue:
            node = queue.pop()
            seen.add(node)
            queue += [b for b in edges.get(node, ()) if b not in seen]
    return count


def lcom4(unit):
    names = [m.name for m in unit["methods"] if m.name not in CONSTRUCTORS]
    edges = {a: [b for b in names if a != b and _linked(unit, a, b)] for a in names}
    return _components(names, edges)


def lcom_hs(unit):
    methods = [m.name for m in unit["methods"] if m.name not in CONSTRUCTORS]
    attrs = unit["fields"]
    if len(methods) <= 1 or not attrs:
        return 0.0
    mu = [sum(1 for m in methods if a in unit["access"][m]) for a in attrs]
    value = (sum(mu) / len(attrs) - len(methods)) / (1 - len(methods))
    return round(max(value, 0.0), 3) + 0.0


def rfc(unit):
    calls = set().union(*(called_names(m) for m in unit["methods"])) if unit["methods"] else set()
    return len(unit["methods"]) + len(calls)


# ---------------------------------------------------------------- успадкування (Лоренц-Кід)

def external_mro_len(dotted, imports):
    """len(__mro__) зовнішнього предка (logging.Formatter, ValueError ...); невідомий -> 2."""
    head, _, rest = dotted.partition(".")
    target = imports.get(head, f"builtins.{head}")
    module_name, attrs = (target, rest) if rest else target.rsplit(".", 1)
    try:
        obj = importlib.import_module(module_name)
        for part in filter(None, attrs.split(".")):
            obj = getattr(obj, part)
        return len(obj.__mro__)
    except (ImportError, AttributeError, TypeError, ValueError):
        return 2


def ancestors(cls, by_name):
    chain, current = [], cls
    while current["bases"] and current["bases"][0] in by_name:
        current = by_name[current["bases"][0]]
        chain.append(current)
    return chain


def dit(cls, by_name):
    """DIT = len(MRO) − 1: клас без явного предка -> 1 (лише object)."""
    chain = ancestors(cls, by_name)
    top = chain[-1] if chain else cls
    external = external_mro_len(top["bases"][0], top["imports"]) if top["bases"] else 1
    return len(chain) + external


def lorenz_kidd(cls, by_name):
    own = {m.name for m in cls["methods"]}
    inherited = set().union(*({m.name for m in a["methods"]} for a in ancestors(cls, by_name))) \
        if ancestors(cls, by_name) else set()
    public = {n for n in own | inherited if not n.startswith("_") or n.startswith("__") and n.endswith("__")}
    return {"pim": len(public), "nma": len(own - inherited), "overridden": len(own & inherited)}


# ---------------------------------------------------------------- MOOD

def is_hidden(name):
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _ratio(a, b):
    return round(a / b, 3) if b else 0.0


def _inherited(cls, by_name, members):
    """Члени предків проєкту, яких клас не перевизначив."""
    parents = ancestors(cls, by_name)
    inherited = set().union(*(members(a) for a in parents)) if parents else set()
    return len(inherited - members(cls))


def _is_client(c, d, eff, by_name):
    uses = any(x.endswith((":" + d["name"], "." + d["name"])) for x in eff[unit_id(c)])
    return c is not d and uses and d not in ancestors(c, by_name)


def _descendants(classes, by_name):
    children = defaultdict(int)
    for c in classes:
        for a in ancestors(c, by_name):
            children[a["name"]] += 1
    return children


def _method_names(cls):
    return {m.name for m in cls["methods"]}


def _field_names(cls):
    return set(cls["fields"])


def _polymorphism(classes, by_name):
    lk = {c["name"]: lorenz_kidd(c, by_name) for c in classes}
    children = _descendants(classes, by_name)
    base = sum(lk[name]["nma"] * children[name] for name in lk)
    return _ratio(sum(v["overridden"] for v in lk.values()), base)


def _factor(classes, by_name, members, hidden):
    """(частка прихованих, частка успадкованих) для методів або атрибутів."""
    own = [name for c in classes for name in members(c)]
    inherited = sum(_inherited(c, by_name, members) for c in classes)
    return _ratio(sum(map(hidden, own)), len(own)), _ratio(inherited, inherited + len(own))


def mood(classes, eff, by_name):
    tc = len(classes)
    mhf, mif = _factor(classes, by_name, _method_names, is_hidden)
    ahf, aif = _factor(classes, by_name, _field_names, is_hidden)
    clients = sum(_is_client(c, d, eff, by_name) for c in classes for d in classes)
    return {"classes": tc, "MHF": mhf, "AHF": ahf, "MIF": mif, "AIF": aif,
            "COF": _ratio(clients, tc * tc - tc), "PF": _polymorphism(classes, by_name)}


# ---------------------------------------------------------------- звіт

def analyse(paths):
    units = load_units(paths)
    classes = [u for u in units if u["kind"] == "class"]
    by_name = {c["name"]: c for c in classes}
    class_index = {c["name"]: c["file"] for c in classes}
    eff = {unit_id(u): efferent(u, class_index) for u in units}
    rows = []
    for u in units:
        coupled = eff[unit_id(u)] | afferent(u, units, eff)
        row = {"component": unit_id(u), "kind": u["kind"], "methods": len(u["methods"]),
               "wmc": wmc(u), "cbo": len(coupled), "rfc": rfc(u), "lcom4": lcom4(u),
               "lcom_hs": lcom_hs(u), "coupled_with": sorted(coupled)}
        if u["kind"] == "class":
            row.update(dit=dit(u, by_name), noc=sum(1 for c in classes if c["bases"][:1] == [u["name"]]),
                       **lorenz_kidd(u, by_name))
        rows.append(row)
    return rows, mood(classes, eff, by_name)


def sonar_format(rows, system, project="NazarFrazovir_Curs_Project"):
    """Той самий формат, що й відповідь api/measures/component."""
    keys = ("wmc", "cbo", "rfc", "lcom4", "lcom_hs", "dit", "noc", "pim", "overridden")
    comps = [{"key": f"{project}:{r['component']}", "qualifier": "CLS" if r["kind"] == "class" else "FIL",
              "measures": [{"metric": k, "value": str(r[k])} for k in keys if k in r]} for r in rows]
    project_measures = [{"metric": k.lower(), "value": str(v)} for k, v in system.items()]
    return {"component": {"key": project, "qualifier": "TRK", "measures": project_measures},
            "components": comps}


def print_table(rows, system):
    print(f"{'компонент':52} {'WMC':>4} {'CBO':>4} {'RFC':>4} {'LCOM4':>5} {'LCOM-HS':>7} {'DIT':>3}")
    for r in sorted(rows, key=lambda r: -r["cbo"]):
        print(f"{r['component'][:52]:52} {r['wmc']:>4} {r['cbo']:>4} {r['rfc']:>4} {r['lcom4']:>5} "
              f"{r['lcom_hs']:>7} {r.get('dit', '-'):>3}")
    print("\nMOOD:", "  ".join(f"{k}={v}" for k, v in system.items()))


def print_graph(rows, unit):
    row = next(r for r in rows if r["component"] == unit)
    print("flowchart LR")
    print(f'  U["{unit}<br/>CBO={row["cbo"]}"]')
    for i, c in enumerate(row["coupled_with"]):
        arrow = f'  C{i}["{c[2:]}"] --> U' if c.startswith("<-") else f'  U --> C{i}["{c}"]'
        print(arrow)


def main():
    ap = argparse.ArgumentParser(description="CK & MOOD для Python")
    ap.add_argument("paths", nargs="*", default=SOURCES)
    ap.add_argument("--json", help="зберегти у форматі SonarQube api/measures")
    ap.add_argument("--unit", help="файл:Клас (або файл:<module>) — детальний звіт")
    ap.add_argument("--graph", action="store_true", help="Mermaid-граф зв'язків для --unit")
    args = ap.parse_args()
    rows, system = analyse(args.paths)
    if args.unit and args.graph:
        print_graph(rows, args.unit)
    elif args.unit:
        print(json.dumps(next(r for r in rows if r["component"] == args.unit), ensure_ascii=False, indent=2))
    else:
        print_table(rows, system)
    if args.json:
        out = safe_path(args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(sonar_format(rows, system), fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
