from flask import Blueprint, abort, current_app, render_template, url_for
from flask_login import current_user, login_required

from app.routes._helpers import oid_or_404, placeholder
from app.services.inventory_queries import get_categories_with_counts

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/")
@login_required
def index():
    db = current_app.db
    categories = get_categories_with_counts(db, current_user.household_id)
    totals = {
        "count": sum(c["count"] for c in categories),
        "invested": sum(c["invested"] for c in categories),
    }
    return render_template("inventory/index.html", categories=categories, totals=totals)


@inventory_bp.route("/categories/<category_id>")
@login_required
def category(category_id):
    cat = current_app.db.categories.find_one(
        {"_id": oid_or_404(category_id), "household_id": current_user.household_id}
    )
    if not cat:
        abort(404)

    # Fase 2: chips de subcategoria + grid de equipamentos (foto, nome, badges)
    return placeholder(
        cat["name"],
        cat.get("icon", "bi-box"),
        planned=[
            "Chips de subcategoria pra filtrar: " + (", ".join(cat.get("subcategories", [])) or "—"),
            "Grid de equipamentos: foto de capa, nome, marca/modelo",
            "Badges de status (Ativo, Quebrado…) e condição (Perfeito, Sinais de Uso…)",
            "Botão “+ Equipamento” já com a categoria preenchida",
        ],
        phase=2,
        back=("Inventário", url_for("inventory.index")),
    )
