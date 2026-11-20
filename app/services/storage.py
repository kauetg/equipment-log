"""Storage de arquivos atrás de uma interface única (PLANO.md §4).

Nenhuma rota sabe qual backend está por baixo: usa `get_storage()` e guarda no documento
só a *file ref* devolvida por `save()`. Trocar GridFS → R2 = novo backend + script de migração.

file ref (embutida nos documentos):
    {"id": "<str>", "name": "nf.pdf", "content_type": "application/pdf", "size": 123,
     "thumb_id": "<str>|None", "external_url": None, "kind": "manual", "uploaded_at": datetime}
"""

from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app


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


def get_storage():
    app = current_app._get_current_object()
    storage = app.extensions.get("storage")
    if storage is None:
        backend = app.config["STORAGE_BACKEND"]
        if backend not in _BACKENDS:
            raise RuntimeError(f"STORAGE_BACKEND desconhecido: {backend!r} (opções: {list(_BACKENDS)})")
        storage = app.extensions["storage"] = _BACKENDS[backend](app)
    return storage
