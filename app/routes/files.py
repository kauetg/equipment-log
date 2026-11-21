from flask import Blueprint, abort
from flask_login import current_user, login_required

from app.services.storage import FileNotFound, storage_for

files_bp = Blueprint("files", __name__, url_prefix="/files")


# <path:> porque a chave do S3 tem "/" ("<household_id>/<uuid>.jpg")
@files_bp.route("/<path:file_id>")
@login_required
def serve(file_id):
    """Confere o household e entrega o arquivo: S3 → redirect pra URL assinada;
    GridFS → stream direto do Mongo."""
    try:
        return storage_for(file_id).serve(file_id, current_user.household_id)
    except FileNotFound:
        abort(404)
