from app.routes.api import api_bp
from app.routes.auth import auth_bp
from app.routes.equipment import equipment_bp
from app.routes.files import files_bp
from app.routes.inventory import inventory_bp
from app.routes.maintenance import maintenance_bp
from app.routes.orders import orders_bp
from app.routes.reports import reports_bp
from app.routes.settings import settings_bp


def register_blueprints(app):
    app.register_blueprint(inventory_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(api_bp)
