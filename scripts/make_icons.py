"""Gera os ícones do PWA/favicon a partir do glifo (app/static/img/glyph.png).

    python scripts/make_icons.py               # regera os ícones a partir do glyph.png
    python scripts/make_icons.py --from-logo   # (re)cria o glyph.png tirando o texto do logo.png
    python scripts/make_icons.py --glyph arte.png   # usa outro arquivo como glifo (copia pro glyph.png)

Quando o glifo definitivo ficar pronto: salve como PNG (fundo transparente ou branco/creme,
quanto maior melhor) e rode com --glyph. Depois suba o CACHE_VERSION do service worker.
"""
import argparse
import os
import sys

from PIL import Image

IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "static", "img")
GLYPH = os.path.join(IMG_DIR, "glyph.png")
BG = (251, 251, 242)  # creme do app (#fbfbf2) — mesmo background_color do manifest

# arquivo -> (tamanho, fração do lado ocupada pelo glifo, fundo opaco?)
OUTPUTS = {
    "icon-192.png": (192, 0.84, True),
    "icon-512.png": (512, 0.84, True),
    # maskable: o Android recorta em círculo/squircle; o glifo precisa caber na zona segura (80%)
    "icon-maskable-512.png": (512, None, True),
    "apple-touch-icon.png": (180, 0.80, True),
    "favicon-32.png": (32, 0.96, False),
}


def color_to_alpha(im, bg=BG, drop=None):
    """Fundo (bg) vira transparente, preservando o antialias. drop(r,g,b) -> True apaga o pixel."""
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # mais claro que o fundo (branco, halo do antialias) conta como fundo
            r, g, b = min(r, bg[0]), min(g, bg[1]), min(b, bg[2])
            if drop and drop(r, g, b):
                px[x, y] = (0, 0, 0, 0)
                continue
            alpha = 0.0
            for c, k in ((r, bg[0]), (g, bg[1]), (b, bg[2])):
                if k:
                    alpha = max(alpha, (k - c) / k)
            if alpha < 0.03:
                px[x, y] = (0, 0, 0, 0)
                continue
            col = tuple(max(0, min(255, round(k + (c - k) / alpha))) for c, k in ((r, bg[0]), (g, bg[1]), (b, bg[2])))
            px[x, y] = (*col, round(alpha * a))
    im = im.crop(im.getbbox())
    im.thumbnail((1024, 1024), Image.LANCZOS)
    return im


def glyph_from_logo():
    """Logo empilhado sem o nome = palmeiras + telhado. Ícone provisório.
    Fica só o que é verde: o texto roxo e o contorno cinza do antialias dele saem."""
    logo = Image.open(os.path.join(IMG_DIR, "logo.png"))
    return color_to_alpha(logo, drop=lambda r, g, b: g - r < 10 or b - g > 18)


def render(glyph, size, fill, opaque):
    gw, gh = glyph.size
    if fill is None:  # maskable: diagonal do glifo dentro do círculo de 80%
        scale = 0.78 * size / (gw * gw + gh * gh) ** 0.5
    else:
        scale = fill * size / max(gw, gh)
    tw, th = max(1, round(gw * scale)), max(1, round(gh * scale))
    small = glyph.resize((tw, th), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (*BG, 255) if opaque else (0, 0, 0, 0))
    canvas.alpha_composite(small, ((size - tw) // 2, (size - th) // 2))
    return canvas.convert("RGB") if opaque else canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-logo", action="store_true")
    ap.add_argument("--glyph")
    args = ap.parse_args()

    if args.from_logo:
        glyph_from_logo().save(GLYPH)
        print("glyph.png criado a partir do logo.png")
    elif args.glyph:
        color_to_alpha(Image.open(args.glyph)).save(GLYPH)
        print(f"glyph.png criado a partir de {args.glyph}")
    if not os.path.exists(GLYPH):
        sys.exit("Sem app/static/img/glyph.png — rode com --from-logo ou --glyph arquivo.png")

    glyph = Image.open(GLYPH).convert("RGBA")
    for name, (size, fill, opaque) in OUTPUTS.items():
        render(glyph, size, fill, opaque).save(os.path.join(IMG_DIR, name))
        print(f"  {name} ({size}px)")
    render(glyph, 48, 0.96, False).save(os.path.join(IMG_DIR, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    print("  favicon.ico (16/32/48)")


if __name__ == "__main__":
    main()
