from bson import ObjectId
from bson.errors import InvalidId
from flask import abort, render_template


def oid_or_404(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        abort(404)


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
