"""🌱 Integrações futuras (PLANO.md §8). Assinaturas definidas, implementação depois.

Liga/desliga por flag em config.INTEGRATIONS (env INTEGRATION_GUARDIOLA / INTEGRATION_MEDIA_LOGGER).
"""

from flask import current_app


def enabled(name):
    return current_app.config["INTEGRATIONS"].get(name, False)
