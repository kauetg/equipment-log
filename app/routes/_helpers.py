from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import abort, render_template


def oid_or_404(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        abort(404)


def oid_or_none(value):
    try:
        return ObjectId(value) if value else None
    except (InvalidId, TypeError):
        return None


def parse_date(value):
    """'2026-11-21' (input type=date) → datetime UTC | None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_number(value):
    """'1,234.50' / '1234,5' / '' → float | None. Ponto é decimal; vírgula vira ponto só se
    não houver ponto (aceita '87,5' digitado no celular)."""
    value = (value or "").strip().replace(" ", "")
    if not value:
        return None
    if "," in value and "." not in value:
        value = value.replace(",", ".")
    value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def placeholder(title, icon, planned, phase, subtitle=None, back=None, **extra):
    """Página "em construção" padrão — lista o que vai existir ali (do PLANO.md) e em que fase.

    planned: lista de strings (o que a página vai ter)
    back: (label, url) opcional pro botão de voltar
    """
    return render_template(
        "_placeholder.html",
        title=title,
        icon=icon,
        planned=planned,
        phase=phase,
        subtitle=subtitle,
        back=back,
        **extra,
    )
