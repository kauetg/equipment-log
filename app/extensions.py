from flask_login import LoginManager
from pymongo import ASCENDING, DESCENDING, MongoClient

login_manager = LoginManager()


def init_extensions(app):
    client = MongoClient(app.config["MONGO_URI"], tz_aware=True)
    # Guardado no app pra integração com o guardiola (mesmo cluster, outro database)
    # — ver services/integrations/guardiola.py.
    app.mongo_client = client
    app.db = client[app.config["MONGO_DB_NAME"]]

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre para continuar."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(app.db, user_id)


def ensure_indexes(db):
    """Índices das coleções principais. Idempotente — rodado pelo seed, não a cada boot
    (create_index em todo worker do gunicorn é desperdício de round-trip no Atlas)."""
    db.users.create_index("email", unique=True)
    db.categories.create_index([("household_id", ASCENDING), ("order", ASCENDING)])
    db.equipment.create_index([("household_id", ASCENDING), ("category_id", ASCENDING)])
    db.equipment.create_index([("household_id", ASCENDING), ("legacy_id", ASCENDING)], sparse=True)
    db.equipment.create_index("exif_keys", sparse=True)  # 🌱 media_logger
    db.orders.create_index([("household_id", ASCENDING), ("date", DESCENDING)])
    db.orders.create_index("items.equipment_id")
    db.orders.create_index("guardiola_tx_ids", sparse=True)  # 🌱 guardiola
    db.maintenance_logs.create_index([("equipment_id", ASCENDING), ("date", DESCENDING)])
