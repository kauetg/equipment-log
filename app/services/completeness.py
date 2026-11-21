"""Pendências de cadastro: o que falta em cada equipamento.

Nada é marcado como "rascunho" — a pendência é calculada dos campos que já existem e some
sozinha quando o campo é preenchido. Itens vendidos/descartados não entram.
"""

from app.services.inventory_queries import INACTIVE_STATUSES

# Ordem = ordem de exibição. "fix" diz pra onde o atalho leva (ver templates).
CHECKS = [
    {"key": "foto", "label": "Foto", "icon": "bi-camera", "fix": "edit"},
    {"key": "compra", "label": "Compra", "icon": "bi-bag", "fix": "order"},
    {"key": "data", "label": "Data de aquisição", "icon": "bi-calendar-event", "fix": "edit"},
    {"key": "subcategoria", "label": "Subcategoria", "icon": "bi-diagram-2", "fix": "edit"},
    {"key": "marca", "label": "Marca / modelo", "icon": "bi-tag", "fix": "edit"},
]
CHECKS_BY_KEY = {c["key"]: c for c in CHECKS}

# Pedido que conta como "tem compra registrada"
_ACQUISITION_KINDS = ["purchase", "gift"]


def build_context(db, household_id):
    """Dados compartilhados pra checar vários itens com 2 consultas no total."""
    purchased = set(
        db.orders.distinct(
            "items.equipment_id", {"household_id": household_id, "kind": {"$in": _ACQUISITION_KINDS}}
        )
    )
    categories = {c["_id"]: c for c in db.categories.find({"household_id": household_id}, {"subcategories": 1})}
    return {"purchased": purchased, "categories": categories}


def missing_for(equipment, ctx):
    """Lista de chaves de CHECKS que faltam neste equipamento ([] = completo)."""
    if equipment.get("status") in INACTIVE_STATUSES:
        return []
    missing = []
    if not equipment.get("photo"):
        missing.append("foto")
    if equipment["_id"] not in ctx["purchased"]:
        missing.append("compra")
    if not equipment.get("acquired_at"):
        missing.append("data")
    category = ctx["categories"].get(equipment.get("category_id"), {})
    # categoria sem subcategorias (ex.: Celular) não cobra subcategoria
    if category.get("subcategories") and not equipment.get("subcategory"):
        missing.append("subcategoria")
    if not equipment.get("brand") or not equipment.get("model"):
        missing.append("marca")
    return missing


def get_pending(db, household_id):
    """→ (itens incompletos com e["_missing"], contagem por chave). Ordenado: mais pendências primeiro."""
    ctx = build_context(db, household_id)
    items = []
    counts = {c["key"]: 0 for c in CHECKS}
    for e in db.equipment.find(
        {"household_id": household_id, "status": {"$nin": list(INACTIVE_STATUSES)}},
        {"name": 1, "photo": 1, "acquired_at": 1, "subcategory": 1, "brand": 1, "model": 1,
         "category_id": 1, "status": 1, "condition": 1, "created_at": 1},
    ):
        missing = missing_for(e, ctx)
        if missing:
            e["_missing"] = missing
            items.append(e)
            for key in missing:
                counts[key] += 1
    items.sort(key=lambda e: (-len(e["_missing"]), e["name"].lower()))
    return items, counts


def count_incomplete(db, household_id):
    return len(get_pending(db, household_id)[0])
