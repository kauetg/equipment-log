from flask import Blueprint
from flask_login import login_required

from app.routes._helpers import placeholder

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def index():
    return placeholder(
        "Relatórios",
        "bi-bar-chart-line",
        planned=[
            "Investido por categoria e por ano (USD)",
            "Custo de manutenção por item/categoria",
            "Garantias vencendo",
            "🌱 Uso por câmera (dados do media_logger)",
        ],
        phase=5,
    )
