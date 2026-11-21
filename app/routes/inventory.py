import re
import unicodedata

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user, login_required

from app.routes._helpers import oid_or_404
from app.services.inventory_queries import INACTIVE_STATUSES, get_categories_with_counts

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
    attention = list(
        db.equipment.find(
            {
                "household_id": current_user.household_id,
                "condition": {"$in": ["wear", "broken"]},
                "status": {"$nin": list(INACTIVE_STATUSES)},
            },
            {"name": 1, "condition": 1, "photo": 1, "category_id": 1},
        ).sort([("condition", 1), ("name", 1)])
    )
    no_receipt = db.orders.count_documents(
        {"household_id": current_user.household_id, "kind": {"$in": ["purchase", "upgrade"]}, "receipts": {"$size": 0}}
    )
    return render_template(
        "inventory/index.html", categories=categories, totals=totals, attention=attention, no_receipt=no_receipt
    )


@inventory_bp.route("/categories/<category_id>")
@login_required
def category(category_id):
    cat = current_app.db.categories.find_one(
        {"_id": oid_or_404(category_id), "household_id": current_user.household_id}
    )
    if not cat:
        abort(404)

    sub = request.args.get("sub", "")
    show_all = request.args.get("all") == "1"  # inclui vendidos/descartados

    base = {"household_id": current_user.household_id, "category_id": cat["_id"]}
    if not show_all:
        base["status"] = {"$nin": list(INACTIVE_STATUSES)}

    items = list(current_app.db.equipment.find(base).sort("name", 1))

    # Uma seção por subcategoria (estilo "agrupado por país" do program-planner): na ordem
    # configurada na categoria, depois subcategorias soltas (digitadas/importadas) em ordem
    # alfabética, e por último os itens sem subcategoria. Seção vazia não aparece.
    by_sub = {}
    for e in items:
        by_sub.setdefault(e.get("subcategory") or "", []).append(e)
    order = [s for s in cat.get("subcategories", []) if s in by_sub]
    order += sorted(s for s in by_sub if s and s not in order)
    if "" in by_sub:
        order.append("")
    sections = [{"name": s, "slug": _slug(s) or "sem-subcategoria", "items": by_sub[s]} for s in order]
    # ?sub= aceita slug ou nome; se não bater com nenhuma seção, mostra tudo
    active = _slug(sub) if sub else ""
    if active not in {s["slug"] for s in sections}:
        active = ""

    hidden_inactive = 0
    if not show_all:
        hidden_inactive = current_app.db.equipment.count_documents(
            {"household_id": current_user.household_id, "category_id": cat["_id"], "status": {"$in": list(INACTIVE_STATUSES)}}
        )

    return render_template(
        "inventory/category.html",
        cat=cat,
        sections=sections,
        active=active,
        total=len(items),
        show_all=show_all,
        hidden_inactive=hidden_inactive,
    )


def _slug(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
