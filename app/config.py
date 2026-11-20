import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _flag(name):
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes", "on")


class Config:
    MONGO_URI = os.environ.get("MONGO_URI")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "equipment_log")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB por request (manual em PDF pode ser grande)

    # Backend de arquivos (ver services/storage.py). MVP = GridFS; "r2" quando crescer.
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "gridfs")

    # 🌱 Integrações futuras (PLANO.md §8) — desligadas até serem implementadas.
    # Mesmo cluster Atlas → o guardiola é lido pelo mesmo MongoClient, só outro database.
    GUARDIOLA_DB_NAME = os.environ.get("GUARDIOLA_DB_NAME", "finance_app")
    INTEGRATIONS = {
        "guardiola": _flag("INTEGRATION_GUARDIOLA"),
        "media_logger": _flag("INTEGRATION_MEDIA_LOGGER"),
    }


# Todos os valores do app são em USD (decisão: o AppSheet já guardava tudo em USD).
# Moeda/valor original pago na loja é opcional, só anotação (ver PLANO.md §1 orders).
BASE_CURRENCY = "USD"

# Status do equipamento (ciclo de vida) — chave interna em inglês, label em pt-BR
EQUIPMENT_STATUSES = {
    "active": {"label": "Ativo", "color": "success", "icon": "bi-check-circle"},
    "broken": {"label": "Quebrado", "color": "danger", "icon": "bi-x-octagon"},
    "loaned": {"label": "Emprestado", "color": "info", "icon": "bi-arrow-left-right"},
    "sold": {"label": "Vendido", "color": "secondary", "icon": "bi-cash-coin"},
    "discarded": {"label": "Descartado", "color": "dark", "icon": "bi-trash"},
}

# Condição física — vem da última manutenção (resulting_condition)
CONDITIONS = {
    "perfect": {"label": "Perfeito", "color": "#0ca30c"},
    "working": {"label": "Funcionando", "color": "#2166ad"},
    "wear": {"label": "Sinais de Uso", "color": "#fab219"},
    "broken": {"label": "Quebrado", "color": "#d03b3b"},
}

ORDER_KINDS = {
    "purchase": "Compra",
    "sale": "Venda",
    "upgrade": "Upgrade",
    "gift": "Brinde",
}

MAINTENANCE_KINDS = {
    "damage": "Dano",
    "repair": "Reparo",
    "cleaning": "Limpeza",
    "upgrade": "Upgrade",
    "inspection": "Inspeção",
}

DOCUMENT_KINDS = {"warranty": "Garantia", "manual": "Manual", "other": "Outro"}

# Mesma paleta categórica validada do guardiola (settings.py CATEGORY_COLOR_CHOICES)
CATEGORY_COLOR_CHOICES = [
    ("#E87F24", "Laranja"),
    ("#1a9c8a", "Verde-água"),
    ("#2166ad", "Azul"),
    ("#e2584f", "Coral"),
    ("#d9a520", "Dourado"),
    ("#4c9a5b", "Verde"),
    ("#7a5aa6", "Violeta"),
    ("#a86935", "Bronze"),
]

# Spec fields reutilizáveis — a categoria escolhe quais mostrar no form do equipamento
_RAM = {"key": "memoria_ram", "label": "Memória RAM", "unit": "GB", "type": "number"}
_STORAGE = {"key": "storage", "label": "Armazenamento", "unit": "GB", "type": "number"}
_DEPTH = {"key": "depth_range", "label": "Profundidade máx.", "unit": "m", "type": "number"}

# Categorias iniciais (seed) — tiradas do Camera Log.xlsx do AppSheet. Depois do seed,
# quem manda é a coleção `categories` (editável em Configurações > Categorias).
DEFAULT_CATEGORIES = [
    {
        "name": "Camera", "icon": "bi-camera", "color": "#E87F24",
        "subcategories": ["Full Frame", "Lente", "Drone", "Action Cam"],
        "spec_fields": [_STORAGE],
        "has_exif": True,  # 🌱 media_logger: mostra o campo "chaves EXIF" no form
    },
    {
        "name": "Foto Sub", "icon": "bi-water", "color": "#2166ad",
        "subcategories": ["Caixa Estanque", "Flash", "Acessórios", "Hardware"],
        "spec_fields": [_DEPTH],
    },
    {
        "name": "Acessório de Foto", "icon": "bi-sd-card", "color": "#d9a520",
        "subcategories": ["Cartao SD", "Bateria", "Carregador", "Filtro", "Outros"],
        "spec_fields": [_STORAGE],
    },
    {
        "name": "Mergulho", "icon": "bi-life-preserver", "color": "#1a9c8a",
        "subcategories": ["Computador de Mergulho", "Regulador"],
        "spec_fields": [_DEPTH],
    },
    {
        "name": "Computador", "icon": "bi-laptop", "color": "#7a5aa6",
        "subcategories": ["Notebook Edicao", "Notebook Portatil", "Tablet", "E-Reader"],
        "spec_fields": [_RAM, _STORAGE],
    },
    {
        "name": "Celular", "icon": "bi-phone", "color": "#e2584f",
        "subcategories": [],
        "spec_fields": [_RAM, _STORAGE],
        "has_exif": True,
    },
    {
        "name": "Outros Eletrônicos", "icon": "bi-headphones", "color": "#a86935",
        "subcategories": ["Fone de Ouvido", "Smartwatch"],
        "spec_fields": [],
    },
]
