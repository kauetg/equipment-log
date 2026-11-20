"""Queries de leitura do inventário (home / categoria)."""

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
