from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pymongo import DESCENDING

from app.config import CONDITIONS, MAINTENANCE_KINDS
from app.routes._helpers import oid_or_404, parse_date, parse_number
from app.services.maintenance import after_log_change
from app.services.storage import delete_ref, save_upload

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


def _household_users():
    return list(current_app.db.users.find({"household_id": current_user.household_id}, {"name": 1}).sort("name", 1))


def _get_equipment_or_404(equipment_id):
    e = current_app.db.equipment.find_one({"_id": oid_or_404(equipment_id), "household_id": current_user.household_id})
    if not e:
        abort(404)
    return e


def _get_log_or_404(log_id):
    log = current_app.db.maintenance_logs.find_one({"_id": oid_or_404(log_id), "household_id": current_user.household_id})
    if not log:
        abort(404)
    return log


def _read_form(users):
    form = request.form
    errors = []

    date = parse_date(form.get("date"))
    if not date:
        errors.append("Data é obrigatória.")
    title = form.get("title", "").strip()
    if not title:
        errors.append("Título é obrigatório.")
    condition = form.get("resulting_condition")
    if condition not in CONDITIONS:
        errors.append("Escolha a condição em que o equipamento ficou.")
    kind = form.get("kind") if form.get("kind") in MAINTENANCE_KINDS else None

    cost = parse_number(form.get("cost"))
    if form.get("cost", "").strip() and (cost is None or cost < 0):
        errors.append("Custo inválido (use número, ex.: 87.50).")

    # Quem fez: um usuário do household, ou texto livre ("Assistência Sony")
    done_by_user = next((u for u in users if str(u["_id"]) == form.get("done_by")), None)
    if done_by_user:
        done_by = {"user_id": done_by_user["_id"], "name": done_by_user["name"]}
    else:
        name = form.get("done_by_other", "").strip()
        done_by = {"user_id": None, "name": name} if name else None

    return {
        "date": date,
        "title": title,
        "kind": kind,
        "description": form.get("description", "").strip(),
        "cost": round(cost, 2) if cost else 0,
        "done_by": done_by,
        "resulting_condition": condition,
    }, errors


def _apply_photos(update, existing=None):
    household_id = current_user.household_id
    remove_ids = set(request.form.getlist("remove_photo"))
    photos, to_delete = [], []
    for ref in (existing or {}).get("photos", []):
        (to_delete if ref.get("id") in remove_ids else photos).append(ref)
    for f in request.files.getlist("photos"):
        ref = save_upload(f, household_id, kind="maintenance")
        if ref:
            photos.append(ref)
    update["photos"] = photos
    return to_delete


def _render_form(equipment, log=None, form=None, status=200):
    return (
        render_template(
            "maintenance/form.html",
            e=equipment,
            log=log or {},
            form=form,
            users=_household_users(),
            CONDITIONS=CONDITIONS,
            MAINTENANCE_KINDS=MAINTENANCE_KINDS,
        ),
        status,
    )


@maintenance_bp.route("/")
@login_required
def index():
    db = current_app.db
    query = {"household_id": current_user.household_id}
    filters = {k: request.args.get(k, "") for k in ("kind", "condition", "person")}
    if filters["kind"] in MAINTENANCE_KINDS:
        query["kind"] = filters["kind"]
    if filters["condition"] in CONDITIONS:
        query["resulting_condition"] = filters["condition"]
    if filters["person"]:
        query["done_by.name"] = filters["person"]

    logs = list(db.maintenance_logs.find(query).sort([("date", DESCENDING), ("created_at", DESCENDING)]))
    equipment = {
        e["_id"]: e
        for e in db.equipment.find(
            {"_id": {"$in": list({l["equipment_id"] for l in logs})}}, {"name": 1, "photo": 1, "category_id": 1}
        )
    }
    people = sorted(
        n for n in db.maintenance_logs.distinct("done_by.name", {"household_id": current_user.household_id}) if n
    )
    attention = list(
        db.equipment.find(
            {
                "household_id": current_user.household_id,
                "condition": {"$in": ["wear", "broken"]},
                "status": {"$nin": ["sold", "discarded"]},
            },
            {"name": 1, "condition": 1, "photo": 1, "category_id": 1},
        ).sort("name", 1)
    )
    return render_template(
        "maintenance/index.html",
        logs=logs,
        equipment=equipment,
        people=people,
        attention=attention,
        filters=filters,
        CONDITIONS=CONDITIONS,
        MAINTENANCE_KINDS=MAINTENANCE_KINDS,
    )


@maintenance_bp.route("/new/<equipment_id>", methods=["GET", "POST"])
@login_required
def new(equipment_id):
    db = current_app.db
    equipment = _get_equipment_or_404(equipment_id)

    if request.method == "POST":
        fields, errors = _read_form(_household_users())
        if errors:
            for e in errors:
                flash(e, "danger")
            return _render_form(equipment, form=request.form, status=400)
        doc = {
            **fields,
            "household_id": current_user.household_id,
            "equipment_id": equipment["_id"],
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc),
        }
        _apply_photos(doc)
        db.maintenance_logs.insert_one(doc)
        after_log_change(db, equipment["_id"])
        flash("Manutenção registrada.", "success")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id, _anchor="tab-maintenance"))

    return _render_form(equipment)


@maintenance_bp.route("/<log_id>/edit", methods=["GET", "POST"])
@login_required
def edit(log_id):
    db = current_app.db
    log = _get_log_or_404(log_id)
    equipment = _get_equipment_or_404(log["equipment_id"])

    if request.method == "POST":
        fields, errors = _read_form(_household_users())
        if errors:
            for e in errors:
                flash(e, "danger")
            return _render_form(equipment, log, form=request.form, status=400)
        update = {**fields, "updated_at": datetime.now(timezone.utc)}
        old = _apply_photos(update, log)
        db.maintenance_logs.update_one({"_id": log["_id"]}, {"$set": update})
        for ref in old:
            delete_ref(ref)
        after_log_change(db, equipment["_id"])
        flash("Manutenção salva.", "success")
        return redirect(url_for("equipment.detail", equipment_id=equipment["_id"], _anchor="tab-maintenance"))

    return _render_form(equipment, log)


@maintenance_bp.route("/<log_id>/delete", methods=["POST"])
@login_required
def delete(log_id):
    db = current_app.db
    log = _get_log_or_404(log_id)
    for ref in log.get("photos", []):
        delete_ref(ref)
    db.maintenance_logs.delete_one({"_id": log["_id"]})
    after_log_change(db, log["equipment_id"])
    flash("Manutenção excluída.", "success")
    return redirect(url_for("equipment.detail", equipment_id=log["equipment_id"], _anchor="tab-maintenance"))
