import re
import unicodedata
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import CATEGORY_COLOR_CHOICES
from app.routes._helpers import oid_or_404

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/categories")
@login_required
def categories():
    db = current_app.db
    cats = list(db.categories.find({"household_id": current_user.household_id}).sort("order", 1))
    counts = {
        row["_id"]: row["n"]
        for row in db.equipment.aggregate(
            [{"$match": {"household_id": current_user.household_id}}, {"$group": {"_id": "$category_id", "n": {"$sum": 1}}}]
        )
    }
    for c in cats:
        c["equipment_count"] = counts.get(c["_id"], 0)
    return render_template("settings/categories.html", categories=cats)


def _slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _read_category_form():
    form = request.form
    errors = []
    name = form.get("name", "").strip()
    if not name:
        errors.append("Nome é obrigatório.")

    icon = form.get("icon", "").strip() or "bi-box"
    if not icon.startswith("bi-"):
        icon = "bi-" + icon
    color = form.get("color", "")
    if color not in {c for c, _ in CATEGORY_COLOR_CHOICES}:
        color = CATEGORY_COLOR_CHOICES[0][0]

    subcategories = []
    for line in form.get("subcategories", "").splitlines():
        line = line.strip()
        if line and line not in subcategories:
            subcategories.append(line)

    spec_fields = []
    seen = set()
    for label, key, unit, ftype in zip(
        form.getlist("spec_label"), form.getlist("spec_key"), form.getlist("spec_unit"), form.getlist("spec_type")
    ):
        label = label.strip()
        if not label:
            continue
        key = _slug(key.strip() or label)
        if not key or key in seen:
            errors.append(f"Campo de spec “{label}”: chave vazia ou repetida.")
            continue
        seen.add(key)
        spec_fields.append(
            {"key": key, "label": label, "unit": unit.strip(), "type": ftype if ftype in ("number", "text") else "number"}
        )

    return {
        "name": name,
        "icon": icon,
        "color": color,
        "subcategories": subcategories,
        "spec_fields": spec_fields,
        "has_exif": bool(form.get("has_exif")),
    }, errors


def _category_form(cat=None, status=200):
    return (
        render_template("settings/category_form.html", cat=cat or {}, color_choices=CATEGORY_COLOR_CHOICES),
        status,
    )


@settings_bp.route("/categories/new", methods=["GET", "POST"])
@login_required
def new_category():
    db = current_app.db
    if request.method == "POST":
        fields, errors = _read_category_form()
        if db.categories.find_one({"household_id": current_user.household_id, "name": fields["name"]}):
            errors.append("Já existe uma categoria com esse nome.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return _category_form(fields, 400)
        last = db.categories.find_one({"household_id": current_user.household_id}, sort=[("order", -1)])
        db.categories.insert_one(
            {
                **fields,
                "household_id": current_user.household_id,
                "order": (last["order"] + 1) if last else 0,
                "created_at": datetime.now(timezone.utc),
            }
        )
        flash(f"Categoria “{fields['name']}” criada.", "success")
        return redirect(url_for("settings.categories"))
    return _category_form()


def _get_category_or_404(category_id):
    cat = current_app.db.categories.find_one(
        {"_id": oid_or_404(category_id), "household_id": current_user.household_id}
    )
    if not cat:
        abort(404)
    return cat


@settings_bp.route("/categories/<category_id>/edit", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    db = current_app.db
    cat = _get_category_or_404(category_id)
    if request.method == "POST":
        fields, errors = _read_category_form()
        clash = db.categories.find_one(
            {"household_id": current_user.household_id, "name": fields["name"], "_id": {"$ne": cat["_id"]}}
        )
        if clash:
            errors.append("Já existe uma categoria com esse nome.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return _category_form({**fields, "_id": cat["_id"]}, 400)
        db.categories.update_one({"_id": cat["_id"]}, {"$set": fields})
        flash("Categoria salva.", "success")
        return redirect(url_for("settings.categories"))
    return _category_form(cat)


@settings_bp.route("/categories/<category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    db = current_app.db
    cat = _get_category_or_404(category_id)
    n = db.equipment.count_documents({"category_id": cat["_id"]})
    if n:
        flash(f"“{cat['name']}” tem {n} equipamento(s) — mova-os pra outra categoria antes de excluir.", "warning")
    else:
        db.categories.delete_one({"_id": cat["_id"]})
        flash(f"Categoria “{cat['name']}” excluída.", "success")
    return redirect(url_for("settings.categories"))


@settings_bp.route("/categories/<category_id>/move", methods=["POST"])
@login_required
def move_category(category_id):
    """Sobe/desce uma posição (troca o `order` com a vizinha) e renumera 0..n pra não ter buraco."""
    db = current_app.db
    cat = _get_category_or_404(category_id)
    cats = list(db.categories.find({"household_id": current_user.household_id}).sort("order", 1))
    idx = next(i for i, c in enumerate(cats) if c["_id"] == cat["_id"])
    target = idx - 1 if request.form.get("direction") == "up" else idx + 1
    if 0 <= target < len(cats):
        cats[idx], cats[target] = cats[target], cats[idx]
    for order, c in enumerate(cats):
        if c.get("order") != order:
            db.categories.update_one({"_id": c["_id"]}, {"$set": {"order": order}})
    return redirect(url_for("settings.categories"))


@settings_bp.route("/account")
@login_required
def account():
    """Página "Minha conta" pro mobile — no desktop o mesmo conteúdo fica no dropdown da navbar."""
    return render_template("settings/account.html")


@settings_bp.route("/account/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Senha atual incorreta.", "danger")
            return redirect(url_for("settings.change_password"))

        if len(new_password) < 6:
            flash("A nova senha precisa ter pelo menos 6 caracteres.", "danger")
            return redirect(url_for("settings.change_password"))

        if new_password != confirm_password:
            flash("As senhas não coincidem.", "danger")
            return redirect(url_for("settings.change_password"))

        current_app.db.users.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"password_hash": generate_password_hash(new_password)}},
        )
        flash("Senha alterada.", "success")
        return redirect(url_for("inventory.index"))

    return render_template("settings/change_password.html")
