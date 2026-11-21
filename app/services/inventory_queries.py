"""Queries de leitura do inventário (home / categoria)."""

import random

# Fora do inventário "em uso": não contam nos cards nem aparecem na categoria por padrão
INACTIVE_STATUSES = ("sold", "discarded")


def get_categories_with_counts(db, household_id):
    """Categorias na ordem configurada, cada uma com `count` (itens não descartados/vendidos)
    e `invested` (soma do total_cost em USD — cache mantido pelos pedidos/manutenções)."""
    categories = list(db.categories.find({"household_id": household_id}).sort("order", 1))

    stats = {
        row["_id"]: row
        for row in db.equipment.aggregate(
            [
                {"$match": {"household_id": household_id, "status": {"$nin": list(INACTIVE_STATUSES)}}},
                {
                    "$group": {
                        "_id": "$category_id",
                        "count": {"$sum": 1},
                        "invested": {"$sum": {"$ifNull": ["$total_cost", 0]}},
                    }
                },
            ]
        )
    }

    for cat in categories:
        row = stats.get(cat["_id"], {})
        cat["count"] = row.get("count", 0)
        cat["invested"] = row.get("invested", 0)
    return categories


SPOTLIGHT_SIZE = 6


def get_spotlight(db, household_id, categories):
    """Itens do carrossel da home: os favoritos (⭐) com foto, em uso. Sem nenhum favorito,
    sorteia alguns itens com foto pra home não ficar vazia — `is_random` avisa o template.
    Cada item ganha `_category` pra legenda (nome/cor/ícone)."""
    base = {
        "household_id": household_id,
        "status": {"$nin": list(INACTIVE_STATUSES)},
        "photo": {"$ne": None},
    }
    fields = {"name": 1, "brand": 1, "model": 1, "subcategory": 1, "photo": 1,
              "category_id": 1, "total_cost": 1, "favorite": 1}
    items = list(db.equipment.find({**base, "favorite": True}, fields).sort("name", 1))
    is_random = not items
    if is_random:
        pool = list(db.equipment.find(base, fields))
        items = random.sample(pool, min(SPOTLIGHT_SIZE, len(pool)))
    by_id = {c["_id"]: c for c in categories}
    for e in items:
        e["_category"] = by_id.get(e.get("category_id"), {})
    return items, is_random
