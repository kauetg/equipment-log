from flask import Blueprint
from flask_login import login_required

from app.routes._helpers import placeholder

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@maintenance_bp.route("/")
@login_required
def index():
    return placeholder(
        "Manutenção",
        "bi-tools",
        planned=[
            "Timeline de todas as manutenções",
            "Filtros: equipamento, quem fez, tipo, condição resultante",
            "Itens hoje em “Sinais de Uso” ou “Quebrado”",
        ],
        phase=3,
    )
