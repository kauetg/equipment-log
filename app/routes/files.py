from flask import Blueprint, abort, send_file
from flask_login import current_user, login_required

from app.services.storage import FileNotFound, get_storage

files_bp = Blueprint("files", __name__, url_prefix="/files")

# id do arquivo nunca muda (upload novo = id novo), então dá pra cachear "pra sempre" no browser
_CACHE_SECONDS = 60 * 60 * 24 * 365


@files_bp.route("/<file_id>")
@login_required
def serve(file_id):
    try:
        stream, name, content_type = get_storage().open(file_id, current_user.household_id)
    except FileNotFound:
        abort(404)
    return send_file(stream, mimetype=content_type, download_name=name, max_age=_CACHE_SECONDS)
