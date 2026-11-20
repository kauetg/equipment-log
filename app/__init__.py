from flask import Flask, current_app, send_from_directory
from flask_login import current_user

from app.config import CONDITIONS, EQUIPMENT_STATUSES, Config
from app.extensions import init_extensions
from app.routes import register_blueprints


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    init_extensions(app)
    register_blueprints(app)
    _register_pwa_routes(app)
    _register_template_filters(app)
    _register_context_processors(app)

    return app


def _register_context_processors(app):
    @app.context_processor
    def inject_globals():
        ctx = {
            "EQUIPMENT_STATUSES": EQUIPMENT_STATUSES,
            "CONDITIONS": CONDITIONS,
            "INTEGRATIONS": app.config["INTEGRATIONS"],
        }
        if current_user.is_authenticated:
            household = current_app.db.households.find_one(
                {"_id": current_user.household_id}, {"name": 1}
            )
            ctx["account_menu_household_name"] = household["name"] if household else "Equipment Log"
        return ctx


def _register_template_filters(app):
    @app.template_filter("usd")
    def usd_filter(value):
        """usd(2353) -> 'USD 2,353.00'. Tudo no app é USD (ver config.BASE_CURRENCY)."""
        if value is None:
            return "—"
        return f"USD {value:,.2f}"

    @app.template_filter("date_br")
    def date_br_filter(value):
        return value.strftime("%d/%m/%Y") if value else "—"


def _register_pwa_routes(app):
    """Serve manifest/service worker na raiz (scope "/"), não sob /static/."""

    @app.route("/manifest.json")
    def pwa_manifest():
        return send_from_directory(
            app.static_folder, "manifest.json", mimetype="application/manifest+json"
        )

    @app.route("/service-worker.js")
    def pwa_service_worker():
        response = send_from_directory(app.static_folder, "service-worker.js")
        response.headers["Cache-Control"] = "no-cache"
        return response
