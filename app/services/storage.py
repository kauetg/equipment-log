"""Storage de arquivos atrás de uma interface única (PLANO.md §4).

Só arquivos (fotos, recibos, manuais) — os dados continuam no Mongo. Nenhuma rota sabe qual
backend está por baixo: usa `save_upload`/`save_bytes`/`delete_ref`/`file_url` e guarda no
documento só a *file ref*.

Backends:
- "cloudinary": plano grátis sem cartão (CLOUDINARY_URL). Arquivos `authenticated`;
  /files/<id> confere o household e redireciona pra URL assinada.
- "s3": qualquer storage S3-compatível — Cloudflare R2, Backblaze B2, AWS S3.
  Bucket privado; /files/<id> confere o household e redireciona pra uma URL assinada (1 h).
- "gridfs": arquivos dentro do Mongo (testes / fallback sem credenciais).

Arquivo novo vai pro backend configurado (STORAGE_BACKEND); arquivo antigo é lido pelo backend
que o criou — dá pra identificar pelo id (Cloudinary = "cld/…"; chave S3 =
"<household_id>/<uuid>.ext"; GridFS = ObjectId de 24 hex). Assim nada quebra no meio da
migração (scripts/migrate_files.py).

file ref (embutida nos documentos):
    {"id": "<str>", "name": "nf.pdf", "content_type": "application/pdf", "size": 123,
     "thumb_id": "<str>|None", "external_url": None, "kind": "manual", "uploaded_at": datetime}
"""

import io
import os
import re
import uuid
from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, redirect, send_file, url_for
from werkzeug.utils import secure_filename

from app.services.images import process_image

# id não muda nunca (upload novo = id novo) → cache longo no browser
IMMUTABLE_MAX_AGE = 60 * 60 * 24 * 365


class FileNotFound(Exception):
    pass


def _ref(file_id, name, content_type, size, kind):
    return {
        "id": file_id,
        "name": name,
        "content_type": content_type,
        "size": size,
        "thumb_id": None,
        "external_url": None,
        "kind": kind,
        "uploaded_at": datetime.now(timezone.utc),
    }


class GridFSStorage:
    """Arquivos no próprio Mongo (bucket `files`)."""

    name = "gridfs"

    def __init__(self, db):
        self.fs = gridfs.GridFS(db, collection="files")

    @staticmethod
    def owns(file_id):
        return ObjectId.is_valid(file_id or "")

    def save(self, data, name, content_type, household_id, kind=None):
        file_id = self.fs.put(data, filename=name, content_type=content_type, household_id=household_id)
        return _ref(str(file_id), name, content_type, len(data), kind)

    def open(self, file_id, household_id):
        """Devolve (stream, nome, content_type). Só abre arquivo do próprio household."""
        try:
            grid_out = self.fs.get(ObjectId(file_id))
        except (InvalidId, TypeError, gridfs.errors.NoFile):
            raise FileNotFound(file_id)
        if getattr(grid_out, "household_id", None) != household_id:
            raise FileNotFound(file_id)
        return grid_out, grid_out.filename, grid_out.content_type

    def serve(self, file_id, household_id):
        stream, name, content_type = self.open(file_id, household_id)
        return send_file(stream, mimetype=content_type, download_name=name, max_age=IMMUTABLE_MAX_AGE)

    def delete(self, file_id):
        try:
            self.fs.delete(ObjectId(file_id))
        except (InvalidId, TypeError):
            pass


class S3Storage:
    """Bucket S3-compatível privado (R2/B2/S3). Chave = "<household_id>/<uuid>.<ext>", então o
    dono do arquivo está no próprio id e a checagem de household não precisa de consulta."""

    name = "s3"

    def __init__(self, config):
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = config["S3_BUCKET"]
        self.presign_seconds = int(config.get("S3_PRESIGN_SECONDS", 3600))
        self.client = boto3.client(
            "s3",
            endpoint_url=config.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=config.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=config.get("S3_SECRET_ACCESS_KEY"),
            region_name=config.get("S3_REGION") or "auto",
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    @staticmethod
    def owns(file_id):
        return "/" in (file_id or "")

    @staticmethod
    def _belongs(file_id, household_id):
        return (file_id or "").startswith(f"{household_id}/") and ".." not in file_id

    def save(self, data, name, content_type, household_id, kind=None):
        ext = os.path.splitext(name)[1].lower()[:10]
        key = f"{household_id}/{uuid.uuid4().hex}{ext}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # nome original no download; "inline" pra foto/PDF abrir no browser
            ContentDisposition=f'inline; filename="{name}"',
            CacheControl=f"private, max-age={IMMUTABLE_MAX_AGE}, immutable",
        )
        return _ref(key, name, content_type, len(data), kind)

    def open(self, file_id, household_id):
        if not self._belongs(file_id, household_id):
            raise FileNotFound(file_id)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=file_id)
        except self.client.exceptions.NoSuchKey:
            raise FileNotFound(file_id)
        return io.BytesIO(obj["Body"].read()), file_id.rsplit("/", 1)[-1], obj.get("ContentType")

    def serve(self, file_id, household_id):
        """Redireciona pra URL assinada (o arquivo vem direto do bucket, sem passar pelo app).
        O redirect é cacheado pelo browser por um pouco menos que a validade da assinatura."""
        if not self._belongs(file_id, household_id):
            raise FileNotFound(file_id)
        url = self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": file_id}, ExpiresIn=self.presign_seconds
        )
        response = redirect(url, code=302)
        response.headers["Cache-Control"] = f"private, max-age={max(self.presign_seconds - 300, 0)}"
        return response

    def delete(self, file_id):
        self.client.delete_object(Bucket=self.bucket, Key=file_id)


def _clean_folder(value, default="equipment-log"):
    """Nome de pasta seguro: corta comentário colado ("equipment-log# …", que o .env não tira
    sem espaço antes do #), espaços e qualquer caractere fora de letras/números/-/_//."""
    value = (value or "").split("#", 1)[0].strip()
    value = re.sub(r"[^A-Za-z0-9_\-/]", "", value).strip("/")
    value = re.sub(r"/{2,}", "/", value)
    return value or default


class CloudinaryStorage:
    """Cloudinary (plano grátis sem cartão). Os arquivos sobem como `authenticated`: o link
    direto não funciona sem assinatura — o app gera a URL assinada depois de conferir o household.

    id = "cld/<resource_type>/<public_id>", com public_id = "equipment-log/<household_id>/<uuid>"
    (raw/PDF leva a extensão no public_id, exigência do Cloudinary pra arquivos raw).
    Imagens já chegam aqui redimensionadas (images.py), então o Cloudinary é só depósito —
    nenhuma transformação gasta créditos.
    """

    name = "cloudinary"
    PREFIX = "cld/"

    def __init__(self, config):
        from urllib.parse import unquote, urlparse

        import cloudinary

        # Parse explícito: o SDK só lê CLOUDINARY_URL do ambiente na hora do import, e
        # config(cloudinary_url=…) não interpreta a URL — assim não depende da ordem de import.
        parsed = urlparse(config["CLOUDINARY_URL"])
        if parsed.scheme != "cloudinary" or not (parsed.hostname and parsed.username and parsed.password):
            raise RuntimeError("CLOUDINARY_URL inválida (esperado cloudinary://<api_key>:<api_secret>@<cloud_name>)")
        cloudinary.config(
            cloud_name=parsed.hostname,
            api_key=unquote(parsed.username),
            api_secret=unquote(parsed.password),
            secure=True,
        )
        # Pasta própria do app na conta (a mesma conta pode servir outros apps)
        self.FOLDER = _clean_folder(config.get("CLOUDINARY_FOLDER"))

    @classmethod
    def owns(cls, file_id):
        return (file_id or "").startswith(cls.PREFIX)

    @classmethod
    def _split(cls, file_id):
        resource_type, public_id = file_id[len(cls.PREFIX):].split("/", 1)
        if resource_type not in ("image", "raw") or ".." in public_id:
            raise FileNotFound(file_id)
        return resource_type, public_id

    def _check(self, file_id, household_id):
        try:
            resource_type, public_id = self._split(file_id)
        except ValueError:
            raise FileNotFound(file_id)
        # public_id = "<pasta>/<household_id>/<uuid>[.ext]". Confere só o household (penúltimo
        # pedaço) — não a pasta configurada agora, pra arquivos antigos sobreviverem a uma troca
        # de CLOUDINARY_FOLDER (ou a um .env com valor estranho).
        parts = public_id.split("/")
        if len(parts) < 3 or parts[-2] != str(household_id):
            raise FileNotFound(file_id)
        return resource_type, public_id

    def save(self, data, name, content_type, household_id, kind=None):
        import cloudinary.uploader

        resource_type = "image" if content_type.startswith("image/") else "raw"
        public_id = f"{self.FOLDER}/{household_id}/{uuid.uuid4().hex}"
        if resource_type == "raw":
            public_id += os.path.splitext(name)[1].lower()[:10]
        cloudinary.uploader.upload(
            io.BytesIO(data),
            public_id=public_id,
            resource_type=resource_type,
            type="authenticated",
            overwrite=False,
            filename_override=name,
            # contas com "dynamic folders": o caminho no public_id não vira pasta na Media
            # Library — asset_folder garante que apareça em equipment-log/<household>/
            asset_folder=f"{self.FOLDER}/{household_id}",
        )
        return _ref(f"{self.PREFIX}{resource_type}/{public_id}", name, content_type, len(data), kind)

    def _signed_url(self, resource_type, public_id):
        from cloudinary.utils import cloudinary_url

        return cloudinary_url(public_id, resource_type=resource_type, type="authenticated", sign_url=True)[0]

    def open(self, file_id, household_id):
        import urllib.request

        resource_type, public_id = self._check(file_id, household_id)
        try:
            with urllib.request.urlopen(self._signed_url(resource_type, public_id), timeout=30) as resp:
                return io.BytesIO(resp.read()), public_id.rsplit("/", 1)[-1], resp.headers.get("Content-Type")
        except Exception:
            raise FileNotFound(file_id)

    def serve(self, file_id, household_id):
        """URL assinada do Cloudinary é estável (não expira) → o redirect pode ser cacheado."""
        resource_type, public_id = self._check(file_id, household_id)
        response = redirect(self._signed_url(resource_type, public_id), code=302)
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    def delete(self, file_id):
        import cloudinary.uploader

        try:
            resource_type, public_id = self._split(file_id)
        except (ValueError, FileNotFound):
            return
        cloudinary.uploader.destroy(public_id, resource_type=resource_type, type="authenticated", invalidate=True)


_BACKENDS = {
    "gridfs": lambda app: GridFSStorage(app.db),
    "s3": lambda app: S3Storage(app.config),
    "cloudinary": lambda app: CloudinaryStorage(app.config),
}


def _backend(app, name):
    cache = app.extensions.setdefault("storage_backends", {})
    if name not in cache:
        if name not in _BACKENDS:
            raise RuntimeError(f"STORAGE_BACKEND desconhecido: {name!r} (opções: {list(_BACKENDS)})")
        cache[name] = _BACKENDS[name](app)
    return cache[name]


def get_storage():
    """Backend onde arquivos NOVOS são gravados."""
    app = current_app._get_current_object()
    return _backend(app, app.config["STORAGE_BACKEND"])


def storage_for(file_id):
    """Backend que guarda um arquivo existente, pelo formato do id."""
    app = current_app._get_current_object()
    if CloudinaryStorage.owns(file_id):  # antes do S3: o id do Cloudinary também tem "/"
        return _backend(app, "cloudinary")
    if S3Storage.owns(file_id):
        return _backend(app, "s3")
    if GridFSStorage.owns(file_id):
        return _backend(app, "gridfs")
    raise FileNotFound(file_id)


# ---- helpers independentes de backend -------------------------------------------------


def save_upload(file_storage, household_id, kind=None):
    """Salva um arquivo vindo de request.files. Imagem é redimensionada (1600px) e ganha
    thumb (400px), ambas em JPEG; o resto (PDF etc.) vai como veio.
    Devolve a file ref, ou None se o campo veio vazio."""
    if not file_storage or not file_storage.filename:
        return None
    data = file_storage.read()
    if not data:
        return None
    return save_bytes(data, file_storage.filename, file_storage.mimetype, household_id, kind=kind)


def save_bytes(data, filename, content_type, household_id, kind=None):
    """Mesmo tratamento do save_upload, a partir de bytes (usado pelo import do AppSheet)."""
    storage = get_storage()
    name = secure_filename(filename) or "arquivo"
    content_type = content_type or "application/octet-stream"

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
    for file_id in (ref.get("id"), ref.get("thumb_id")):
        if file_id:
            try:
                storage_for(file_id).delete(file_id)
            except FileNotFound:
                pass


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
