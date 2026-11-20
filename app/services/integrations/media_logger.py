"""🌱 Integração com o media_logger (PLANO.md §8.2).

O media_logger lê o EXIF (`Image Make` + `Image Model`) e procura em cameras.json:
    {"SONY - ILCE-7M4": {"name": "Sony a7 IV", "image": "ILCE-7M4K3_400x.webp"}}

Plano: o Equipment Log vira a fonte desses perfis, a partir de `equipment.exif_keys`.
O media_logger baixa /api/cameras.json e cai no arquivo local se estiver offline.
"""


def exif_key(make, model):
    """Mesma chave que o media_logger monta: "SONY - ILCE-7M4"."""
    return f"{str(make).strip()} - {str(model).strip()}"


def export_cameras_json():
    """{exif_key: {"name": equipment.name, "image": url da foto de capa}} pra todo
    equipamento com exif_keys. Proteger com token simples no header antes de ligar."""
    raise NotImplementedError


def detect_exif_keys(image_stream):
    """Lê o EXIF de um JPG enviado no form do equipamento (botão "detectar de uma foto")
    e devolve [exif_key]. Mesma lógica do detect_exif do media_logger (lib exifread)."""
    raise NotImplementedError
