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
    # Produção (Raspberry atrás de proxy HTTPS) — ver README "Deploy no Raspberry Pi"
    BEHIND_PROXY = _flag("BEHIND_PROXY")
    SESSION_COOKIE_SECURE = REMEMBER_COOKIE_SECURE = _flag("COOKIE_SECURE")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB por request (manual em PDF pode ser grande)

    # Arquivos (fotos, recibos, manuais) — ver services/storage.py. Só arquivos; dados ficam no Mongo.
    # "cloudinary" (grátis, sem cartão), "s3" (R2/B2/AWS) ou "gridfs" (dentro do Mongo).
    # Sem STORAGE_BACKEND explícito: o primeiro que estiver configurado COM credenciais.
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")  # cloudinary://<api_key>:<api_secret>@<cloud_name>
    CLOUDINARY_FOLDER = os.environ.get("CLOUDINARY_FOLDER", "equipment-log")  # pasta do app na conta
    S3_BUCKET = os.environ.get("S3_BUCKET")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")  # R2: https://<account_id>.r2.cloudflarestorage.com
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")
    S3_REGION = os.environ.get("S3_REGION", "auto")  # R2 = "auto"
    S3_PRESIGN_SECONDS = int(os.environ.get("S3_PRESIGN_SECONDS", 3600))
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND") or (
        "cloudinary" if CLOUDINARY_URL
        else "s3" if (S3_BUCKET and S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY)
        else "gridfs"
    )

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

# Moedas pra anotar o valor original pago na loja (opcional — o app calcula tudo em USD)
ORIGINAL_CURRENCIES = ["PHP", "SGD", "MYR", "IDR", "THB", "EUR", "BRL", "GBP", "USD"]

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
