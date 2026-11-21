import re
import unicodedata

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user, login_required

from app.routes._helpers import oid_or_404
from app.services.completeness import CHECKS, CHECKS_BY_KEY, build_context, get_pending, missing_for
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
    incomplete = len(get_pending(db, current_user.household_id)[0])
    return render_template(
        "inventory/index.html",
        categories=categories,
        totals=totals,
        attention=attention,
        no_receipt=no_receipt,
        incomplete=incomplete,
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
    ctx = build_context(current_app.db, current_user.household_id)
    for e in items:
        e["_missing"] = missing_for(e, ctx)

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


@inventory_bp.route("/pending")
@login_required
def pending():
    """Itens com cadastro incompleto. ?falta=foto|compra|data|subcategoria|marca filtra."""
    db = current_app.db
    all_items, counts = get_pending(db, current_user.household_id)
    falta = request.args.get("falta", "")
    if falta not in CHECKS_BY_KEY:
        falta = ""
    items = [e for e in all_items if falta in e["_missing"]] if falta else all_items
    categories = {c["_id"]: c for c in db.categories.find({"household_id": current_user.household_id})}
    return render_template(
        "inventory/pending.html",
        items=items,
        counts=counts,
        total=len(all_items),
        falta=falta,
        categories=categories,
        CHECKS=CHECKS,
        CHECKS_BY_KEY=CHECKS_BY_KEY,
    )


def _slug(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
