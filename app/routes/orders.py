from flask import Blueprint, url_for
from flask_login import login_required

from app.routes._helpers import oid_or_404, placeholder

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.route("/")
@login_required
def index():
    return placeholder(
        "Pedidos",
        "bi-bag",
        planned=[
            "Lista de compras, vendas, upgrades e brindes",
            "Filtro por loja/contraparte e ano",
            "🌱 Ícone 🔗 / ⚠️ de pagamento vinculado no Guardiola (fila de conciliação)",
        ],
        phase=3,
    )


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    return placeholder(
        "Novo pedido",
        "bi-bag-plus",
        planned=[
            "Tipo* (Compra / Venda / Upgrade / Brinde), data*, loja (datalist), plataforma",
            "Total em USD* (moeda e valor original opcionais)",
            "Lista de itens: equipamento existente ou “novo item rápido”, valor de cada (0 = brinde)",
            "Recibos (múltiplos), notas",
            "Venda marca os itens como Vendido",
        ],
        phase=3,
        back=("Pedidos", url_for("orders.index")),
    )


@orders_bp.route("/<order_id>")
@login_required
def detail(order_id):
    oid_or_404(order_id)
    return placeholder(
        "Pedido",
        "bi-receipt",
        planned=[
            "Itens, valores, loja, recibos",
            "🌱 Card “Pagamento”: transações do Guardiola vinculadas ou botão “Vincular”",
        ],
        phase=3,
        back=("Pedidos", url_for("orders.index")),
    )
