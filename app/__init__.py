import os

from flask import Flask, current_app, send_from_directory
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import current_user

from app.config import (
    CONDITIONS,
    DOCUMENT_KINDS,
    EQUIPMENT_STATUSES,
    MAINTENANCE_KINDS,
    ORDER_KINDS,
    Config,
)
from app.extensions import init_extensions
from app.services.completeness import CHECKS, CHECKS_BY_KEY
from app.routes import register_blueprints


MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    if app.config.get("BEHIND_PROXY"):
        # Atrás de nginx/Caddy/Cloudflare Tunnel no Raspberry: confia no X-Forwarded-* pra
        # url_for e redirects saírem com https e o host público.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
            "MAINTENANCE_KINDS": MAINTENANCE_KINDS,
            "ORDER_KINDS": ORDER_KINDS,
            "DOCUMENT_KINDS": DOCUMENT_KINDS,
            "CHECKS": CHECKS,
            "CHECKS_BY_KEY": CHECKS_BY_KEY,
            "INTEGRATIONS": app.config["INTEGRATIONS"],
            # Logos (já trazem o nome): logo.png empilhado (home) e logo_horizontal.png (navbar,
            # login). Checados a cada render pra aparecerem assim que o arquivo for colocado em
            # static/img/, sem reiniciar o servidor.
            "LOGOS": {
                name: os.path.exists(os.path.join(app.static_folder, "img", f"{name}.png"))
                for name in ("logo", "logo_horizontal")
            },
        }
        if current_user.is_authenticated:
            household = current_app.db.households.find_one(
                {"_id": current_user.household_id}, {"name": 1}
            )
            ctx["account_menu_household_name"] = household["name"] if household else "Pataka"
        return ctx


def _register_template_filters(app):
    from app.services.storage import file_url, is_image

    app.jinja_env.globals.update(file_url=file_url, is_image=is_image)

    @app.template_filter("usd")
    def usd_filter(value, decimals=2):
        """usd(2353) -> 'USD 2,353.00'. Tudo no app é USD (ver config.BASE_CURRENCY).
        Sai embrulhado em .money pro modo "ocultar valores" (menu da conta) trocar por ••••."""
        if value is None:
            return "—"
        return money_markup(f"USD {value:,.{decimals}f}")

    app.jinja_env.globals.update(money=money_markup)

    @app.template_filter("day_month")
    def day_month_filter(value):
        """14 nov — dia + mês abreviado em pt, pra listas onde o ano já aparece em destaque."""
        return f"{value.day} {MONTHS_PT[value.month - 1]}" if value else "—"

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

    @app.route("/favicon.ico")
    def pwa_favicon():
        return send_from_directory(
            os.path.join(app.static_folder, "img"), "favicon.ico", mimetype="image/vnd.microsoft.icon"
        )

    @app.route("/service-worker.js")
    def pwa_service_worker():
        response = send_from_directory(app.static_folder, "service-worker.js")
        response.headers["Cache-Control"] = "no-cache"
        return response


def money_markup(text):
    """Valor em dinheiro com a versão mascarada do lado; o CSS mostra uma ou outra conforme
    <html class="hide-money"> (ligado no menu da conta, guardado no localStorage do aparelho)."""
    text = escape(text)
    mask = escape(text.split(" ")[0] + " ••••") if " " in text else "••••"
    return Markup(f'<span class="money"><span class="money-val">{text}</span><span class="money-mask">{mask}</span></span>')
