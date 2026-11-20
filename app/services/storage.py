"""Storage de arquivos atrás de uma interface única (PLANO.md §4).

Nenhuma rota sabe qual backend está por baixo: usa `get_storage()` e guarda no documento
só a *file ref* devolvida por `save()`. Trocar GridFS → R2 = novo backend + script de migração.

file ref (embutida nos documentos):
    {"id": "<str>", "name": "nf.pdf", "content_type": "application/pdf", "size": 123,
     "thumb_id": "<str>|None", "external_url": None, "kind": "manual", "uploaded_at": datetime}
"""

import os
from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, url_for
from werkzeug.utils import secure_filename

from app.services.images import process_image


class FileNotFound(Exception):
    pass


class GridFSStorage:
    """MVP: arquivos no próprio Mongo (bucket `files`). Cabe com folga no Atlas free pro
    volume atual (~90 arquivos redimensionados)."""

    def __init__(self, db):
        self.fs = gridfs.GridFS(db, collection="files")

    def save(self, data, name, content_type, household_id, kind=None):
        """data: bytes ou file-like. Devolve a file ref (sem thumb — ver images.py, fase 2)."""
        file_id = self.fs.put(
            data, filename=name, content_type=content_type, household_id=household_id
        )
        return {
            "id": str(file_id),
            "name": name,
            "content_type": content_type,
            "size": self.fs.get(file_id).length,
            "thumb_id": None,
            "external_url": None,
            "kind": kind,
            "uploaded_at": datetime.now(timezone.utc),
        }

    def open(self, file_id, household_id):
        """Devolve (stream, nome, content_type). Só abre arquivo do próprio household."""
        try:
            grid_out = self.fs.get(ObjectId(file_id))
        except (InvalidId, TypeError, gridfs.errors.NoFile):
            raise FileNotFound(file_id)
        if getattr(grid_out, "household_id", None) != household_id:
            raise FileNotFound(file_id)
        return grid_out, grid_out.filename, grid_out.content_type

    def delete(self, file_id):
        try:
            self.fs.delete(ObjectId(file_id))
        except (InvalidId, TypeError):
            pass


_BACKENDS = {"gridfs": lambda app: GridFSStorage(app.db)}


# ---- helpers independentes de backend -------------------------------------------------


def save_upload(file_storage, household_id, kind=None):
    """Salva um arquivo vindo de request.files. Imagem é redimensionada (1600px) e ganha
    thumb (400px), ambas em JPEG; o resto (PDF etc.) vai como veio.
    Devolve a file ref, ou None se o campo veio vazio."""
    if not file_storage or not file_storage.filename:
        return None

    storage = get_storage()
    data = file_storage.read()
    if not data:
        return None
    name = secure_filename(file_storage.filename) or "arquivo"
    content_type = file_storage.mimetype or "application/octet-stream"

    processed = process_image(data) if content_type.startswith("image/") else None
    if processed:
        main, thumb = processed
        stem = os.path.splitext(name)[0] or "foto"
        ref = storage.save(main, f"{stem}.jpg", "image/jpeg", household_id, kind=kind)
        thumb_ref = storage.save(thumb, f"{stem}.thumb.jpg", "image/jpeg", household_id, kind="thumb")
        ref["thumb_id"] = thumb_ref["id"]
        return ref

    return storage.save(data, name, content_type, household_id, kind=kind)


def external_ref(url, kind=None):
    """File ref que só aponta pra uma URL externa (ex.: foto do AppSheet vinda do Google)."""
    return {
        "id": None,
        "name": url.rsplit("/", 1)[-1][:80] or "link",
        "content_type": None,
        "size": None,
        "thumb_id": None,
        "external_url": url,
        "kind": kind,
        "uploaded_at": datetime.now(timezone.utc),
    }


def delete_ref(ref):
    """Apaga o arquivo e a thumb de uma ref (refs externas não têm nada pra apagar)."""
    if not ref:
        return
    storage = get_storage()
    for file_id in (ref.get("id"), ref.get("thumb_id")):
        if file_id:
            storage.delete(file_id)


def file_url(ref, thumb=False):
    """URL pra usar em <img>/<a>. Registrado como global do Jinja (app/__init__.py)."""
    if not ref:
        return None
    if ref.get("external_url"):
        return ref["external_url"]
    file_id = (ref.get("thumb_id") if thumb else None) or ref.get("id")
    return url_for("files.serve", file_id=file_id) if file_id else None


def is_image(ref):
    if not ref:
        return False
    if ref.get("external_url"):
        return True  # só usamos link externo pra foto
    return (ref.get("content_type") or "").startswith("image/")


def get_storage():
    app = current_app._get_current_object()
    storage = app.extensions.get("storage")
    if storage is None:
        backend = app.config["STORAGE_BACKEND"]
        if backend not in _BACKENDS:
            raise RuntimeError(f"STORAGE_BACKEND desconhecido: {backend!r} (opções: {list(_BACKENDS)})")
        storage = app.extensions["storage"] = _BACKENDS[backend](app)
    return storage
