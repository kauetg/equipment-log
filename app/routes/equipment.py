import re
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.config import (
    CONDITIONS,
    DOCUMENT_KINDS,
    EQUIPMENT_STATUSES,
    MAINTENANCE_KINDS,
    ORDER_KINDS,
)
from app.routes._helpers import oid_or_404, parse_date, parse_number
from app.services.completeness import build_context, missing_for
from app.services.orders import sync_after_order_change
from app.services.integrations.media_logger import exif_key
from app.services.storage import delete_ref, external_ref, save_upload

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")


# ---- helpers -------------------------------------------------------------------------


def _categories():
    return list(
        current_app.db.categories.find({"household_id": current_user.household_id}).sort("order", 1)
    )


def _get_equipment_or_404(equipment_id):
    doc = current_app.db.equipment.find_one(
        {"_id": oid_or_404(equipment_id), "household_id": current_user.household_id}
    )
    if not doc:
        abort(404)
    return doc


def _all_spec_fields(categories):
    """Spec fields únicos por key, cada um com a lista de categorias que usam (pro JS mostrar/esconder)."""
    fields = {}
    for cat in categories:
        for f in cat.get("spec_fields", []):
            entry = fields.setdefault(f["key"], {**f, "category_ids": []})
            entry["category_ids"].append(str(cat["_id"]))
    return list(fields.values())


def _form_context(categories, equipment=None, form=None):
    db = current_app.db
    brands = sorted(
        b for b in db.equipment.distinct("brand", {"household_id": current_user.household_id}) if b
    )
    counterparties = sorted(
        c for c in db.orders.distinct("counterparty", {"household_id": current_user.household_id}) if c
    )
    return {
        "categories": categories,
        "spec_fields": _all_spec_fields(categories),
        "brands": brands,
        "counterparties": counterparties,
        "equipment": equipment or {},
        "form": form,
        "EQUIPMENT_STATUSES": EQUIPMENT_STATUSES,
        "DOCUMENT_KINDS": DOCUMENT_KINDS,
    }


def _read_form(categories, existing=None):
    """Lê request.form → (campos, erros). Não mexe em arquivos (ver _apply_files)."""
    form = request.form
    errors = []

    name = form.get("name", "").strip()
    if not name:
        errors.append("Nome é obrigatório.")

    category = next((c for c in categories if str(c["_id"]) == form.get("category_id")), None)
    if not category:
        errors.append("Escolha uma categoria.")

    status = form.get("status", "active")
    if status not in EQUIPMENT_STATUSES:
        status = "active"

    # Specs que não são da categoria atual (ex.: trocou de categoria, ou veio do import) ficam
    # guardadas; os campos da categoria atual são sobrescritos pelo form (vazio = apaga).
    current_keys = [f["key"] for f in category.get("spec_fields", [])] if category else []
    specs = {k: v for k, v in (existing or {}).get("specs", {}).items() if k not in current_keys}
    for f in category.get("spec_fields", []) if category else []:
        raw = form.get(f"spec__{f['key']}", "")
        value = parse_number(raw) if f.get("type") == "number" else (raw.strip() or None)
        if value is not None:
            specs[f["key"]] = value

    exif_keys = []
    if category and category.get("has_exif"):
        for line in re.split(r"[\n;]+", form.get("exif_keys", "")):
            line = line.strip()
            if not line:
                continue
            # formato do media_logger: "MAKE - MODEL" (normaliza espaços)
            if " - " in line:
                make, model = line.split(" - ", 1)
                line = exif_key(make, model)
            exif_keys.append(line)
    elif existing:
        exif_keys = existing.get("exif_keys", [])

    fields = {
        "name": name,
        "brand": form.get("brand", "").strip(),
        "model": form.get("model", "").strip(),
        "serial_number": form.get("serial_number", "").strip(),
        "category_id": category["_id"] if category else None,
        "subcategory": form.get("subcategory", "").strip(),
        "status": status,
        "acquired_at": parse_date(form.get("acquired_at")),
        "specs": specs,
        "specs_text": form.get("specs_text", "").strip(),
        "notes": form.get("notes", "").strip(),
        "exif_keys": exif_keys,
    }
    return fields, category, errors


def _read_purchase():
    """Bloco "registrar compra agora" do cadastro. Devolve dict ou None."""
    form = request.form
    if not form.get("register_purchase"):
        return None, []
    amount = parse_number(form.get("purchase_amount"))
    if amount is None or amount < 0:
        return None, ["Valor da compra inválido (use número, ex.: 2353.50)."]
    return {
        "date": parse_date(form.get("purchase_date")),
        "amount": round(amount, 2),
        "counterparty": form.get("purchase_counterparty", "").strip(),
        "platform": form.get("purchase_platform", "").strip(),
        "notes": form.get("purchase_notes", "").strip(),
    }, []


def _apply_files(doc_update, existing):
    """Processa foto de capa e documentos do form. Retorna as refs antigas que devem ser apagadas
    do storage (só apaga depois que o update no Mongo deu certo)."""
    household_id = current_user.household_id
    to_delete = []
    existing = existing or {}

    # Foto de capa: upload > URL externa > remover > mantém
    photo_upload = save_upload(request.files.get("photo"), household_id, kind="photo")
    photo_url = request.form.get("photo_url", "").strip()
    current_photo = existing.get("photo")
    if photo_upload:
        doc_update["photo"] = photo_upload
        to_delete.append(current_photo)
    elif photo_url and photo_url != (current_photo or {}).get("external_url"):
        doc_update["photo"] = external_ref(photo_url, kind="photo")
        to_delete.append(current_photo)
    elif request.form.get("remove_photo"):
        doc_update["photo"] = None
        to_delete.append(current_photo)

    # Documentos: remove os marcados, adiciona os novos
    remove_ids = set(request.form.getlist("remove_document"))
    documents = []
    for ref in existing.get("documents", []):
        if ref.get("id") in remove_ids:
            to_delete.append(ref)
        else:
            documents.append(ref)
    for kind in DOCUMENT_KINDS:
        for f in request.files.getlist(f"document_{kind}"):
            ref = save_upload(f, household_id, kind=kind)
            if ref:
                documents.append(ref)
    doc_update["documents"] = documents

    return [r for r in to_delete if r]


# ---- rotas ---------------------------------------------------------------------------


@equipment_bp.route("/")
@login_required
def index():
    db = current_app.db
    categories = _categories()
    cats_by_id = {c["_id"]: c for c in categories}

    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "")
    status = request.args.get("status", "")

    query = {"household_id": current_user.household_id}
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"brand": pattern}, {"model": pattern}, {"serial_number": pattern}]
    if category_id:
        query["category_id"] = oid_or_404(category_id)
    if status in EQUIPMENT_STATUSES:
        query["status"] = status

    items = list(db.equipment.find(query).sort([("name", 1)]))
    return render_template(
        "equipment/index.html",
        items=items,
        categories=categories,
        cats_by_id=cats_by_id,
        filters={"q": q, "category": category_id, "status": status},
    )


@equipment_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    db = current_app.db
    categories = _categories()

    if request.method == "POST":
        fields, category, errors = _read_form(categories)
        purchase, purchase_errors = _read_purchase()
        errors += purchase_errors
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("equipment/form.html", **_form_context(categories, form=request.form)), 400

        now = datetime.now(timezone.utc)
        if purchase and not fields["acquired_at"]:
            fields["acquired_at"] = purchase["date"]
        doc = {
            **fields,
            "household_id": current_user.household_id,
            "condition": None,
            "photo": None,
            "documents": [],
            "gallery": [],
            "total_cost": 0,
            "legacy_id": None,
            "created_by": current_user.id,
            "created_at": now,
            "updated_at": now,
        }
        _apply_files(doc, None)
        equipment_id = db.equipment.insert_one(doc).inserted_id
        _remember_subcategory(category, fields["subcategory"])

        if purchase:
            order = {
                    "household_id": current_user.household_id,
                    "kind": "purchase" if purchase["amount"] > 0 else "gift",
                    "date": purchase["date"] or fields["acquired_at"] or now,
                    "counterparty": purchase["counterparty"],
                    "platform": purchase["platform"],
                    "currency": "USD",
                    "total": purchase["amount"],
                    "items": [{"equipment_id": equipment_id, "amount": purchase["amount"]}],
                    "receipts": [],
                    "notes": purchase["notes"],
                    "guardiola_tx_ids": [],  # 🌱 PLANO.md §8.1
                    "created_by": current_user.id,
                    "created_at": now,
            }
            order["_id"] = db.orders.insert_one(order).inserted_id
            sync_after_order_change(db, None, order)

        if request.form.get("after") == "another":
            # "Salvar e cadastrar outro": volta pro form vazio mantendo categoria/subcategoria
            flash(f"“{fields['name']}” cadastrado — próximo!", "success")
            return redirect(
                url_for("equipment.new", category=fields["category_id"], sub=fields["subcategory"] or None)
            )
        flash(f"“{fields['name']}” cadastrado.", "success")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    preset = {}
    if request.args.get("category"):
        preset["category_id"] = request.args["category"]
    if request.args.get("sub"):
        preset["subcategory"] = request.args["sub"]
    return render_template("equipment/form.html", **_form_context(categories, form=preset or None))


@equipment_bp.route("/<equipment_id>/edit", methods=["GET", "POST"])
@login_required
def edit(equipment_id):
    db = current_app.db
    equipment = _get_equipment_or_404(equipment_id)
    categories = _categories()

    if request.method == "POST":
        fields, category, errors = _read_form(categories, existing=equipment)
        if errors:
            for e in errors:
                flash(e, "danger")
            return (
                render_template("equipment/form.html", **_form_context(categories, equipment, form=request.form)),
                400,
            )

        update = {**fields, "updated_at": datetime.now(timezone.utc)}
        old_refs = _apply_files(update, equipment)
        db.equipment.update_one({"_id": equipment["_id"]}, {"$set": update})
        for ref in old_refs:
            delete_ref(ref)
        _remember_subcategory(category, fields["subcategory"])

        flash("Alterações salvas.", "success")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    return render_template("equipment/form.html", **_form_context(categories, equipment))


@equipment_bp.route("/<equipment_id>")
@login_required
def detail(equipment_id):
    db = current_app.db
    equipment = _get_equipment_or_404(equipment_id)
    category = db.categories.find_one({"_id": equipment.get("category_id")}) or {}

    orders = list(db.orders.find({"items.equipment_id": equipment["_id"]}).sort("date", -1))
    for o in orders:
        o["item_amount"] = next(
            (i.get("amount") for i in o["items"] if i["equipment_id"] == equipment["_id"]), None
        )
        o["other_items"] = len(o["items"]) - 1
    logs = list(
        db.maintenance_logs.find({"equipment_id": equipment["_id"]}).sort([("date", -1), ("created_at", -1)])
    )

    # Aba Arquivos: tudo que tem anexo ligado ao item, agrupado pela origem
    receipts = [(o, r) for o in orders for r in o.get("receipts", [])]
    maintenance_photos = [(log, p) for log in logs for p in log.get("photos", [])]

    spec_labels = {}
    for cat in db.categories.find({"household_id": current_user.household_id}, {"spec_fields": 1}):
        for f in cat.get("spec_fields", []):
            spec_labels.setdefault(f["key"], f)

    return render_template(
        "equipment/detail.html",
        e=equipment,
        category=category,
        receipts=receipts,
        maintenance_photos=maintenance_photos,
        missing=missing_for(equipment, build_context(db, current_user.household_id)),
        orders=orders,
        logs=logs,
        spec_labels=spec_labels,
        ORDER_KINDS=ORDER_KINDS,
        MAINTENANCE_KINDS=MAINTENANCE_KINDS,
        DOCUMENT_KINDS=DOCUMENT_KINDS,
        CONDITIONS=CONDITIONS,
    )


@equipment_bp.route("/<equipment_id>/delete", methods=["POST"])
@login_required
def delete(equipment_id):
    db = current_app.db
    equipment = _get_equipment_or_404(equipment_id)

    # Pedido com outros itens só perde este item; pedido só com ele é apagado junto.
    for order in db.orders.find({"items.equipment_id": equipment["_id"]}):
        remaining = [i for i in order["items"] if i["equipment_id"] != equipment["_id"]]
        if remaining:
            db.orders.update_one({"_id": order["_id"]}, {"$set": {"items": remaining}})
        else:
            for ref in order.get("receipts", []):
                delete_ref(ref)
            db.orders.delete_one({"_id": order["_id"]})
    for log in db.maintenance_logs.find({"equipment_id": equipment["_id"]}):
        for ref in log.get("photos", []):
            delete_ref(ref)
    db.maintenance_logs.delete_many({"equipment_id": equipment["_id"]})

    for ref in [equipment.get("photo"), *equipment.get("documents", []), *equipment.get("gallery", [])]:
        delete_ref(ref)
    db.equipment.delete_one({"_id": equipment["_id"]})

    flash(f"“{equipment['name']}” excluído.", "success")
    if equipment.get("category_id"):
        return redirect(url_for("inventory.category", category_id=equipment["category_id"]))
    return redirect(url_for("inventory.index"))


@equipment_bp.route("/<equipment_id>/gallery", methods=["POST"])
@login_required
def add_gallery(equipment_id):
    equipment = _get_equipment_or_404(equipment_id)
    refs = [
        ref
        for f in request.files.getlist("photos")
        if (ref := save_upload(f, current_user.household_id, kind="gallery"))
    ]
    if refs:
        current_app.db.equipment.update_one({"_id": equipment["_id"]}, {"$push": {"gallery": {"$each": refs}}})
        flash(f"{len(refs)} foto(s) adicionada(s).", "success")
    else:
        flash("Nenhum arquivo escolhido.", "warning")
    return redirect(url_for("equipment.detail", equipment_id=equipment_id, _anchor="tab-files"))


@equipment_bp.route("/<equipment_id>/gallery/<file_id>/delete", methods=["POST"])
@login_required
def delete_gallery(equipment_id, file_id):
    equipment = _get_equipment_or_404(equipment_id)
    ref = next((r for r in equipment.get("gallery", []) if r.get("id") == file_id), None)
    if not ref:
        abort(404)
    current_app.db.equipment.update_one({"_id": equipment["_id"]}, {"$pull": {"gallery": {"id": file_id}}})
    delete_ref(ref)
    flash("Foto removida.", "success")
    return redirect(url_for("equipment.detail", equipment_id=equipment_id, _anchor="tab-files"))


@equipment_bp.route("/<equipment_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(equipment_id):
    """Liga/desliga a estrelinha. Favoritos vão pro carrossel da home."""
    equipment = _get_equipment_or_404(equipment_id)
    favorite = not equipment.get("favorite", False)
    current_app.db.equipment.update_one({"_id": equipment["_id"]}, {"$set": {"favorite": favorite}})
    nxt = request.form.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for("equipment.detail", equipment_id=equipment_id))


@equipment_bp.route("/<equipment_id>/cover/<file_id>", methods=["POST"])
@login_required
def set_cover(equipment_id, file_id):
    """Promove uma foto da galeria a capa (a capa antiga volta pra galeria)."""
    equipment = _get_equipment_or_404(equipment_id)
    gallery = equipment.get("gallery", [])
    ref = next((r for r in gallery if r.get("id") == file_id), None)
    if not ref:
        abort(404)
    new_gallery = [r for r in gallery if r.get("id") != file_id]
    if equipment.get("photo") and not equipment["photo"].get("external_url"):
        new_gallery.insert(0, equipment["photo"])
    current_app.db.equipment.update_one(
        {"_id": equipment["_id"]}, {"$set": {"photo": {**ref, "kind": "photo"}, "gallery": new_gallery}}
    )
    flash("Foto de capa atualizada.", "success")
    return redirect(url_for("equipment.detail", equipment_id=equipment_id, _anchor="tab-files"))


def _remember_subcategory(category, subcategory):
    """Subcategoria nova digitada no form entra na lista da categoria (aparece no datalist e nos chips)."""
    if category and subcategory and subcategory not in category.get("subcategories", []):
        current_app.db.categories.update_one(
            {"_id": category["_id"]}, {"$addToSet": {"subcategories": subcategory}}
        )
