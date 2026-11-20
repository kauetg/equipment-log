from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("inventory.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.get_by_email(current_app.db, email)
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            session.permanent = True
            return redirect(_safe_next(request.args.get("next")) or url_for("inventory.index"))

        flash("Email ou senha inválidos.", "danger")

    return render_template("auth/login.html")


def _safe_next(target):
    """Só aceita caminho interno ("/orders/…") — nada de "//site.com" ou "https://…"."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
