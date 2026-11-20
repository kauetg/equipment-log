"""Efeitos colaterais de um pedido (compra/venda/upgrade/brinde) nos equipamentos."""

from app.services.equipment_costs import recompute_total_cost


def _item_ids(order):
    return {i["equipment_id"] for i in (order or {}).get("items", [])}


def sync_after_order_change(db, before, after):
    """Chamar depois de criar (before=None), editar ou excluir (after=None) um pedido.

    - recalcula total_cost de todo item que entrou ou saiu;
    - venda: itens viram `sold`; item que saiu de uma venda (ou venda excluída / virou outro
      tipo) volta pra `active` se ainda estava `sold` e não está em nenhuma outra venda;
    - compra: preenche acquired_at do item com a data do pedido, se estiver vazio.
    """
    affected = _item_ids(before) | _item_ids(after)

    sold_now = _item_ids(after) if after and after.get("kind") == "sale" else set()
    was_sold = _item_ids(before) if before and before.get("kind") == "sale" else set()

    if sold_now:
        db.equipment.update_many({"_id": {"$in": list(sold_now)}}, {"$set": {"status": "sold"}})
    for equipment_id in was_sold - sold_now:
        other_sale = db.orders.find_one(
            {"kind": "sale", "items.equipment_id": equipment_id, **({"_id": {"$ne": after["_id"]}} if after else {})}
        )
        if not other_sale:
            db.equipment.update_one({"_id": equipment_id, "status": "sold"}, {"$set": {"status": "active"}})

    if after and after.get("kind") in ("purchase", "gift") and after.get("date"):
        db.equipment.update_many(
            {"_id": {"$in": list(_item_ids(after))}, "acquired_at": None},
            {"$set": {"acquired_at": after["date"]}},
        )

    for equipment_id in affected:
        recompute_total_cost(db, equipment_id)
