"""Efeitos colaterais de um log de manutenção no equipamento."""

from pymongo import DESCENDING

from app.services.equipment_costs import recompute_total_cost


def recompute_condition(db, equipment_id):
    """equipment.condition = condição resultante do log mais recente (por data; empate → o
    último registrado). Sem logs → None."""
    latest = db.maintenance_logs.find_one(
        {"equipment_id": equipment_id, "resulting_condition": {"$ne": None}},
        sort=[("date", DESCENDING), ("created_at", DESCENDING)],
    )
    condition = latest["resulting_condition"] if latest else None
    db.equipment.update_one({"_id": equipment_id}, {"$set": {"condition": condition}})
    return condition


def after_log_change(db, equipment_id):
    recompute_condition(db, equipment_id)
    recompute_total_cost(db, equipment_id)
