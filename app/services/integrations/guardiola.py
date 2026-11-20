"""🌱 Integração com o guardiola (PLANO.md §8.1) — a mais importante.

Princípio: o guardiola é a fonte da verdade do dinheiro. O Equipment Log só *aponta* pra
transação via `orders.guardiola_tx_ids`. Começar SÓ LENDO; escrita cruzada (create_expense)
fica pra depois e precisa de decisão explícita.

Mesmo cluster Atlas → lê pelo mesmo MongoClient, database `GUARDIOLA_DB_NAME`.

Formato de uma transação no guardiola (routes/transactions.py de lá):
    household_id, wallet_id, type ("expense"|"income"|"transfer"), amount_original,
    currency_original, amount_wallet, amount_usd, category, description, date,
    project_id, is_refundable
Os dois lados estão em USD (orders.total ↔ transactions.amount_usd), o que simplifica o match.
"""

from flask import current_app

MATCH_AMOUNT_TOLERANCE = 0.02  # ±2% no amount_usd
MATCH_DAYS_WINDOW = 5  # ±5 dias na data


def guardiola_db():
    app = current_app._get_current_object()
    return app.mongo_client[app.config["GUARDIOLA_DB_NAME"]]


def suggest_matches(order):
    """Transações do guardiola candidatas a pagar este pedido.
    expense (ou income, se order.kind == "sale") com |amount_usd - total| <= 2% e data ±5 dias,
    excluindo as já vinculadas a outro pedido."""
    raise NotImplementedError


def link(order_id, tx_id):
    """$addToSet em orders.guardiola_tx_ids."""
    raise NotImplementedError


def unlink(order_id, tx_id):
    """$pull em orders.guardiola_tx_ids."""
    raise NotImplementedError


def get_linked(order):
    """Transações vinculadas, com nome da carteira e valor original — pro card "Pagamento"."""
    raise NotImplementedError


def create_expense(order, wallet_id, category):
    """(Fase posterior) cria a despesa no guardiola a partir do pedido. Escreve no banco
    de outro app — só depois de decidir isso explicitamente."""
    raise NotImplementedError
