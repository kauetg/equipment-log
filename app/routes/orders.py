import re
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pymongo import DESCENDING

from app.config import ORDER_KINDS, ORIGINAL_CURRENCIES
from app.routes._helpers import oid_or_404, oid_or_none, parse_date, parse_number
from app.services.orders import sync_after_order_change
from app.services.storage import delete_ref, save_upload

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")

PLATFORMS = ["Lazada", "Shopee", "Amazon", "Loja física", "Site oficial", "Mercado Livre", "OLX"]


def _get_order_or_404(order_id):
    order = current_app.db.orders.find_one({"_id": oid_or_404(order_id), "household_id": current_user.household_id})
    if not order:
        abort(404)
    return order


def _equipment_choices():
    """Equipamentos agrupados por categoria pro <select> dos itens."""
    db = current_app.db
    hid = current_user.household_id
    categories = list(db.categories.find({"household_id": hid}).sort("order", 1))
    equipment = list(db.equipment.find({"household_id": hid}, {"name": 1, "category_id": 1, "status": 1}).sort("name", 1))
    groups = []
    for cat in categories:
        items = [e for e in equipment if e.get("category_id") == cat["_id"]]
        if items:
            groups.append((cat["name"], items))
    orphans = [e for e in equipment if e.get("category_id") not in {c["_id"] for c in categories}]
    if orphans:
        groups.append(("Sem categoria", orphans))
    return categories, groups


def _read_form(categories):
    """→ (campos, novos_itens, erros). novos_itens = [(índice, nome, category_id)] pra criar
    equipamento "rápido" — só depois de validar tudo."""
    form = request.form
    errors = []
    hid = current_user.household_id

    kind = form.get("kind")
    if kind not in ORDER_KINDS:
        errors.append("Escolha o tipo (compra, venda…).")
    date = parse_date(form.get("date"))
    if not date:
        errors.append("Data é obrigatória.")

    valid_equipment = {
        e["_id"] for e in current_app.db.equipment.find({"household_id": hid}, {"_id": 1})
    }
    category_ids = {str(c["_id"]): c["_id"] for c in categories}

    items, new_items = [], []
    rows = zip(
        form.getlist("item_equipment"),
        form.getlist("item_new_name"),
        form.getlist("item_new_category"),
        form.getlist("item_amount"),
    )
    for idx, (equipment_ref, new_name, new_category, amount_raw) in enumerate(rows):
        new_name = new_name.strip()
        if not equipment_ref and not new_name:
            continue  # linha vazia
        amount = parse_number(amount_raw)
        if amount_raw.strip() and (amount is None or amount < 0):
            errors.append(f"Item {idx + 1}: valor inválido.")
            continue
        amount = 0.0 if kind == "gift" else round(amount or 0, 2)

        if equipment_ref == "__new__" or (not equipment_ref and new_name):
            if not new_name or new_category not in category_ids:
                errors.append(f"Item {idx + 1}: novo item precisa de nome e categoria.")
                continue
            new_items.append((len(items), new_name, category_ids[new_category]))
            items.append({"equipment_id": None, "amount": amount})
        else:
            eid = oid_or_none(equipment_ref)
            if eid not in valid_equipment:
                errors.append(f"Item {idx + 1}: equipamento inválido.")
                continue
            if any(i["equipment_id"] == eid for i in items):
                errors.append(f"Item {idx + 1}: equipamento repetido.")
                continue
            items.append({"equipment_id": eid, "amount": amount})

    if not items:
        errors.append("Adicione pelo menos um item.")

    original_currency = form.get("original_currency", "")
    original_total = parse_number(form.get("original_total"))
    has_original = original_currency in ORIGINAL_CURRENCIES and original_total is not None

    return {
        "kind": kind,
        "date": date,
        "counterparty": form.get("counterparty", "").strip(),
        "platform": form.get("platform", "").strip(),
        "currency": "USD",
        "items": items,
        "total": round(sum(i["amount"] for i in items), 2),
        "original_currency": original_currency if has_original else None,
        "original_total": round(original_total, 2) if has_original else None,
        "notes": form.get("notes", "").strip(),
    }, new_items, errors


def _create_quick_equipment(new_items, fields):
    """Cria os equipamentos "novo item rápido" e encaixa os ids nos itens do pedido."""
    db = current_app.db
    now = datetime.now(timezone.utc)
    for index, name, category_id in new_items:
        eid = db.equipment.insert_one(
            {
                "household_id": current_user.household_id,
                "name": name,
                "brand": "", "model": "", "serial_number": "", "subcategory": "",
                "category_id": category_id,
                "status": "active",
                "condition": None,
                "acquired_at": None,
                "specs": {}, "specs_text": "", "notes": "", "exif_keys": [],
                "photo": None, "documents": [], "gallery": [],
                "total_cost": 0,
                "legacy_id": None,
                "created_by": current_user.id,
                "created_at": now,
                "updated_at": now,
            }
        ).inserted_id
        fields["items"][index]["equipment_id"] = eid
    return len(new_items)


def _apply_receipts(update, existing=None):
    remove_ids = set(request.form.getlist("remove_receipt"))
    receipts, to_delete = [], []
    for ref in (existing or {}).get("receipts", []):
        (to_delete if ref.get("id") in remove_ids else receipts).append(ref)
    for f in request.files.getlist("receipts"):
        ref = save_upload(f, current_user.household_id, kind="receipt")
        if ref:
            receipts.append(ref)
    update["receipts"] = receipts
    return to_delete


def _render_form(order=None, form=None, status=200):
    db = current_app.db
    categories, groups = _equipment_choices()
    hid = current_user.household_id
    preset_equipment = request.args.get("equipment", "")
    return (
        render_template(
            "orders/form.html",
            order=order or {},
            form=form,
            categories=categories,
            equipment_groups=groups,
            preset_equipment=preset_equipment,
            preset_kind=request.args.get("kind", "purchase"),
            counterparties=sorted(c for c in db.orders.distinct("counterparty", {"household_id": hid}) if c),
            platforms=sorted(set(PLATFORMS) | {p for p in db.orders.distinct("platform", {"household_id": hid}) if p}),
            currencies=ORIGINAL_CURRENCIES,
        ),
        status,
    )


def _form_rows(form):
    """Linhas de item pra re-renderizar o form depois de erro (mantém o que foi digitado)."""
    return [
        {"equipment": e, "new_name": n, "new_category": c, "amount": a}
        for e, n, c, a in zip(
            form.getlist("item_equipment"), form.getlist("item_new_name"),
            form.getlist("item_new_category"), form.getlist("item_amount"),
        )
    ]


# ---- rotas ---------------------------------------------------------------------------


@orders_bp.route("/")
@login_required
def index():
    db = current_app.db
    hid = current_user.household_id
    filters = {k: request.args.get(k, "") for k in ("kind", "year", "q")}

    query = {"household_id": hid}
    if filters["kind"] in ORDER_KINDS:
        query["kind"] = filters["kind"]
    if filters["year"].isdigit():
        y = int(filters["year"])
        query["date"] = {"$gte": datetime(y, 1, 1, tzinfo=timezone.utc), "$lt": datetime(y + 1, 1, 1, tzinfo=timezone.utc)}
    if filters["q"]:
        pattern = {"$regex": re.escape(filters["q"]), "$options": "i"}
        # Também acha pelo equipamento (nome, marca, modelo) — é o que aparece em destaque na lista
        eq_ids = db.equipment.distinct(
            "_id",
            {"household_id": hid, "$or": [{"name": pattern}, {"brand": pattern}, {"model": pattern}]},
        )
        query["$or"] = [
            {"counterparty": pattern},
            {"platform": pattern},
            {"notes": pattern},
            {"items.equipment_id": {"$in": eq_ids}},
        ]

    orders = list(db.orders.find(query).sort([("date", DESCENDING), ("created_at", DESCENDING)]))
    equipment = {
        e["_id"]: e
        for e in db.equipment.find(
            {"_id": {"$in": list({i["equipment_id"] for o in orders for i in o["items"]})}},
            {"name": 1, "photo": 1, "category_id": 1},
        )
    }
    years = sorted({o["date"].year for o in db.orders.find({"household_id": hid}, {"date": 1}) if o.get("date")}, reverse=True)
    totals = {
        "spent": sum(o["total"] for o in orders if o["kind"] in ("purchase", "upgrade")),
        "received": sum(o["total"] for o in orders if o["kind"] == "sale"),
    }
    return render_template(
        "orders/index.html", orders=orders, equipment=equipment, years=years, filters=filters, totals=totals
    )


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    db = current_app.db
    if request.method == "POST":
        categories = list(db.categories.find({"household_id": current_user.household_id}))
        fields, new_items, errors = _read_form(categories)
        if errors:
            for e in errors:
                flash(e, "danger")
            return _render_form(form={**request.form.to_dict(), "rows": _form_rows(request.form)}, status=400)
        _create_quick_equipment(new_items, fields)
        now = datetime.now(timezone.utc)
        doc = {
            **fields,
            "household_id": current_user.household_id,
            "guardiola_tx_ids": [],  # 🌱 PLANO.md §8.1
            "created_by": current_user.id,
            "created_at": now,
        }
        _apply_receipts(doc)
        doc["_id"] = db.orders.insert_one(doc).inserted_id
        sync_after_order_change(db, None, doc)
        flash(f"{ORDER_KINDS[doc['kind']]} registrada.", "success")
        return redirect(url_for("orders.detail", order_id=doc["_id"]))
    return _render_form()


@orders_bp.route("/<order_id>")
@login_required
def detail(order_id):
    db = current_app.db
    order = _get_order_or_404(order_id)
    equipment = {
        e["_id"]: e
        for e in db.equipment.find({"_id": {"$in": [i["equipment_id"] for i in order["items"]]}})
    }
    categories = {c["_id"]: c for c in db.categories.find({"household_id": current_user.household_id})}
    return render_template("orders/detail.html", o=order, equipment=equipment, categories=categories)


@orders_bp.route("/<order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    db = current_app.db
    order = _get_order_or_404(order_id)
    if request.method == "POST":
        categories = list(db.categories.find({"household_id": current_user.household_id}))
        fields, new_items, errors = _read_form(categories)
        if errors:
            for e in errors:
                flash(e, "danger")
            return _render_form(order, form={**request.form.to_dict(), "rows": _form_rows(request.form)}, status=400)
        _create_quick_equipment(new_items, fields)
        update = {**fields, "updated_at": datetime.now(timezone.utc)}
        old_receipts = _apply_receipts(update, order)
        db.orders.update_one({"_id": order["_id"]}, {"$set": update})
        for ref in old_receipts:
            delete_ref(ref)
        sync_after_order_change(db, order, {**order, **update})
        flash("Salvo.", "success")
        return redirect(url_for("orders.detail", order_id=order_id))
    return _render_form(order)


@orders_bp.route("/<order_id>/delete", methods=["POST"])
@login_required
def delete(order_id):
    db = current_app.db
    order = _get_order_or_404(order_id)
    for ref in order.get("receipts", []):
        delete_ref(ref)
    db.orders.delete_one({"_id": order["_id"]})
    sync_after_order_change(db, order, None)
    flash("Excluído (os equipamentos continuam no inventário).", "success")
    return redirect(url_for("orders.index"))
