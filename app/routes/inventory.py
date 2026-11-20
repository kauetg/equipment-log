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
    return render_template("inventory/index.html", categories=categories, totals=totals)


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

    items = list(current_app.db.equipment.find({**base, **({"subcategory": sub} if sub else {})}).sort("name", 1))

    # Contagem por subcategoria pros chips (respeitando o filtro de inativos)
    sub_counts = {}
    for row in current_app.db.equipment.aggregate([{"$match": base}, {"$group": {"_id": "$subcategory", "n": {"$sum": 1}}}]):
        sub_counts[row["_id"] or ""] = row["n"]
    hidden_inactive = 0
    if not show_all:
        hidden_inactive = current_app.db.equipment.count_documents(
            {"household_id": current_user.household_id, "category_id": cat["_id"], "status": {"$in": list(INACTIVE_STATUSES)}}
        )

    return render_template(
        "inventory/category.html",
        cat=cat,
        items=items,
        sub=sub,
        sub_counts=sub_counts,
        total=sum(sub_counts.values()),
        show_all=show_all,
        hidden_inactive=hidden_inactive,
    )
