"""ЛР10: юніт-тести аудитора актуальності документації."""
from scripts import doc_audit as da

BLUEPRINT_SRC = '''
bp = Blueprint("api", __name__, url_prefix="/api")
inv = Blueprint('inv', __name__)

@bp.get("/balance")
def balance(): ...

@inv.post('/movements/<int:rid>/cancel')
def cancel(rid): ...

app.add_url_rule("/", endpoint="dashboard", view_func=dashboard)
'''

COMPOSE = """
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
  web:
    build: .
    environment:
      DB_CONNECT_TIMEOUT: "2"

volumes:
  pg_data:
"""


def test_routes_combine_blueprint_prefix():
    assert sorted(da.routes_in(BLUEPRINT_SRC)) == [
        ("GET", "/"), ("GET", "/api/balance"), ("POST", "/movements/<int:rid>/cancel")]


def test_compose_services_and_env():
    assert da.compose_services(COMPOSE) == ["db", "web"]
    names = {a or b for a, b in da.ENV_COMPOSE_RE.findall(COMPOSE)}
    assert names == {"POSTGRES_DB", "DB_CONNECT_TIMEOUT"}


def test_missing_reports_only_absent_items(tmp_path):
    doc = tmp_path / "sdd.md"
    doc.write_text("Маршрут `/api/balance` описано.", encoding="utf-8")
    assert da.missing(["/api/balance", "/api/health"], doc) == ["/api/health"]
    assert da.missing(["x"], tmp_path / "absent.md") == ["x"]


def metrics(age, behind, kind="product", review=90, refs=1, consumer="так"):
    m = da.DocMetrics({"kind": kind, "review_days": review, "consumer": consumer})
    m.age_days, m.code_behind, m.refs = age, behind, refs
    return da.classify(m)


def test_classification_thresholds():
    assert metrics(10, 0) == []
    assert "підозрілий (>90 дн.)" in metrics(120, 0, review=180)
    assert any("застарілий" in f for f in metrics(370, 0))
    assert any("структурний дрейф" in f for f in metrics(5, 21))
    assert metrics(5, 2) == ["відстає від коду на 2 коміт(и)"]
    assert metrics(5, 2, kind="process", review=None) == []            # процесні не «відстають»
    assert any("Dead" in f for f in metrics(5, 0, refs=0, consumer=None))


def test_gate_ignores_dead_flag_but_not_drift():
    passport = da.DocMetrics({"path": "docs/sdd.md", "passport": True}, flags=["без споживача (Dead Documentation?)"])
    assert da.gate_failures([passport], {"SDD": []}) == []
    passport.flags.append("відстає від коду на 1 коміт(и)")
    assert len(da.gate_failures([passport], {"SDD": ["/api/x"]})) == 2


def test_gate_uses_review_cycle_not_generic_age():
    arch = da.DocMetrics({"path": "docs/sdd.md", "passport": True}, flags=["підозрілий (>90 дн.)"])
    assert da.gate_failures([arch], {}) == []
    arch.flags.append("прострочено перегляд (180 дн.)")
    assert da.gate_failures([arch], {}) == ["docs/sdd.md: прострочено перегляд (180 дн.)"]
