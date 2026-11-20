"""🌱 API pra integrações (PLANO.md §8). Nada habilitado ainda."""

from flask import Blueprint, abort, current_app

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/cameras.json")
def cameras():
    """Perfis de câmera no formato do cameras.json do media_logger, gerados a partir de
    equipment.exif_keys. Fica 404 até a integração ser ligada (INTEGRATION_MEDIA_LOGGER=1)."""
    if not current_app.config["INTEGRATIONS"]["media_logger"]:
        abort(404)

    from app.services.integrations import media_logger

    return media_logger.export_cameras_json()
