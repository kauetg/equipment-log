"""Cache `equipment.total_cost` (USD) = itens de compra/upgrade nos pedidos + custo das manutenções.

Chamado sempre que um pedido ou manutenção que envolve o equipamento muda. Venda não entra
(é dinheiro voltando, não custo) — o "lucro/prejuízo" de uma venda fica pros relatórios.
"""

COST_ORDER_KINDS = ("purchase", "upgrade", "gift")


def recompute_total_cost(db, equipment_id):
    orders_total = next(
        db.orders.aggregate(
            [
                {"$match": {"items.equipment_id": equipment_id, "kind": {"$in": list(COST_ORDER_KINDS)}}},
                {"$unwind": "$items"},
                {"$match": {"items.equipment_id": equipment_id}},
                {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$items.amount", 0]}}}},
            ]
        ),
        {},
    ).get("total", 0)

    maintenance_total = next(
        db.maintenance_logs.aggregate(
            [
                {"$match": {"equipment_id": equipment_id}},
                {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$cost", 0]}}}},
            ]
        ),
        {},
    ).get("total", 0)

    total = round(orders_total + maintenance_total, 2)
    db.equipment.update_one({"_id": equipment_id}, {"$set": {"total_cost": total}})
    return total
