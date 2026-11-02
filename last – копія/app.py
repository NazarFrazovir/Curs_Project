import os

from dotenv import load_dotenv
from flask import Flask

from api import bp as api_bp
from auth import bp as auth_bp
from dashboard import dashboard, inject_globals
from db import release_conn
from inventory import bp as inv_bp
from reports import bp as reports_bp
from privacy import configure_logging, init_app as init_privacy

load_dotenv()
configure_logging()

BLUEPRINTS = (auth_bp, inv_bp, reports_bp, api_bp)


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_secret")

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
    init_privacy(app)

    # endpoint "dashboard" збережено, щоб url_for('dashboard') у шаблонах працював
    app.add_url_rule("/", endpoint="dashboard", view_func=dashboard)
    app.context_processor(inject_globals)
    app.teardown_appcontext(release_conn)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
