from bson import ObjectId
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/categories")
@login_required
def categories():
    # Fase 2: CRUD (nome, ícone, cor, ordem, subcategorias, spec_fields). Por ora só leitura.
    cats = list(
        current_app.db.categories.find({"household_id": current_user.household_id}).sort("order", 1)
    )
    return render_template("settings/categories.html", categories=cats)


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
