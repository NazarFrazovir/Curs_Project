import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from api import bp as api_bp
from auth import bp as auth_bp
from dashboard import dashboard, inject_globals
import db
from db import release_conn
from inventory import bp as inv_bp
from reports import bp as reports_bp
from privacy import configure_logging, init_app as init_privacy

load_dotenv()
configure_logging()

BLUEPRINTS = (auth_bp, inv_bp, reports_bp, api_bp)
APP_VERSION = os.environ.get("APP_VERSION", "dev")
POD_NAME = os.environ.get("HOSTNAME", "local")  # у Kubernetes HOSTNAME = ім'я пода


def healthz():
    """Liveness: процес живий, БД не перевіряється (для livenessProbe у Kubernetes)."""
    return jsonify(status="ok", version=APP_VERSION, pod=POD_NAME)


def readyz():
    """Readiness: застосунок готовий приймати трафік, лише якщо відповідає БД."""
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        return jsonify(status="unavailable", version=APP_VERSION), 503
    return jsonify(status="ready", version=APP_VERSION)


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_secret")

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
    init_privacy(app)

    # endpoint "dashboard" збережено, щоб url_for('dashboard') у шаблонах працював
    app.add_url_rule("/", endpoint="dashboard", view_func=dashboard)
    app.add_url_rule("/healthz", endpoint="healthz", view_func=healthz)
    app.add_url_rule("/readyz", endpoint="readyz", view_func=readyz)
    app.context_processor(inject_globals)
    app.context_processor(lambda: {"app_version": APP_VERSION})
    app.teardown_appcontext(release_conn)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
