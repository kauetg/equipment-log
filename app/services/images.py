"""Redimensionamento de fotos no upload (PLANO.md §4): foto de celular de ~8 MB vira ~300 KB."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600
THUMB_SIDE = 400
JPEG_QUALITY = 85

# Formatos que vale a pena reprocessar. GIF (animação) e SVG passam direto.
_RESIZABLE = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "MPO"}


def _to_jpeg(img, side):
    img = img.copy()
    img.thumbnail((side, side), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        # PNG com transparência: fundo branco em vez de preto
        background = Image.new("RGB", img.size, "white")
        if "A" in img.getbands():
            background.paste(img, mask=img.getchannel("A"))
        else:
            background.paste(img.convert("RGB"))
        img = background
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def process_image(data):
    """bytes → (main_jpeg, thumb_jpeg) ou None se não for imagem que dá pra processar.
    Aplica a rotação do EXIF (foto de celular deitada) antes de redimensionar."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in _RESIZABLE:
            return None
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return _to_jpeg(img, MAX_SIDE), _to_jpeg(img, THUMB_SIDE)
