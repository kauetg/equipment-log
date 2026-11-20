from flask import Blueprint, url_for
from flask_login import login_required

from app.routes._helpers import oid_or_404, placeholder

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")


@equipment_bp.route("/")
@login_required
def index():
    return placeholder(
        "Equipamentos",
        "bi-list-ul",
        planned=[
            "Tabela com busca por nome, marca, modelo e nº de série",
            "Filtros: categoria, subcategoria, status, condição",
            "Alternar entre tabela e grid",
        ],
        phase=2,
    )


@equipment_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    return placeholder(
        "Novo equipamento",
        "bi-plus-circle",
        planned=[
            "Nome*, categoria* → subcategoria (select dependente)",
            "Marca (datalist), modelo, nº de série, data de aquisição, status",
            "Bloco de specs que muda conforme a categoria (RAM, armazenamento, profundidade…)",
            "Foto de capa (câmera do celular), garantia e manual (PDF)",
            "Checkbox “registrar compra agora” → cria o pedido junto",
            "🌱 Chaves EXIF (Camera/Celular) + “detectar de uma foto”",
        ],
        phase=2,
        back=("Inventário", url_for("inventory.index")),
    )


@equipment_bp.route("/<equipment_id>")
@login_required
def detail(equipment_id):
    oid_or_404(equipment_id)
    return placeholder(
        "Detalhe do equipamento",
        "bi-camera",
        planned=[
            "Header: foto, marca/modelo, nº de série, badges de status e condição",
            "Aba Visão geral: specs, notas, garantia e manual",
            "Aba Manutenção: timeline dos logs + “+ Manutenção”",
            "Aba Compras/Vendas: pedidos que incluem este item",
            "Aba Arquivos: galeria e documentos",
        ],
        phase=3,
        back=("Inventário", url_for("inventory.index")),
    )


@equipment_bp.route("/<equipment_id>/edit", methods=["GET", "POST"])
@login_required
def edit(equipment_id):
    oid_or_404(equipment_id)
    return placeholder(
        "Editar equipamento",
        "bi-pencil",
        planned=["Mesmo form do cadastro, preenchido"],
        phase=2,
        back=("Detalhe", url_for("equipment.detail", equipment_id=equipment_id)),
    )


@equipment_bp.route("/<equipment_id>/maintenance/new", methods=["GET", "POST"])
@login_required
def new_maintenance(equipment_id):
    oid_or_404(equipment_id)
    return placeholder(
        "Nova manutenção",
        "bi-tools",
        planned=[
            "Data*, título*, tipo (Dano, Reparo, Limpeza, Upgrade, Inspeção)",
            "Descrição, custo (USD), quem fez (Kauê / Bárbara / outro)",
            "Condição resultante* — 4 botões: Perfeito, Funcionando, Sinais de Uso, Quebrado",
            "Fotos (múltiplas)",
        ],
        phase=3,
        back=("Detalhe", url_for("equipment.detail", equipment_id=equipment_id)),
    )
