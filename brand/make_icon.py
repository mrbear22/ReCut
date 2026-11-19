"""Знак ReCut: «RE» над «CUT» на шматку жовтої стрічки — як логотип у шапці.
Контури літер — зі шрифту Dela Gothic One (OFL), тож знак однаковий у будь-якому розмірі й не залежить від шрифтів у системі.

    pip install fonttools pillow
    python brand/make_icon.py DelaGothicOne-Regular.ttf brand launcher/icon.ico

Пише brand/logo.svg (для інтерфейсу), brand/logo-1024.png, brand/sizes.png (перевірка малих розмірів) і launcher/icon.ico."""
import math, sys
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from brands import polygons                                       # той самий розбір контурів SVG, що й для логотипів мереж

INK, PAPER, TAPE, TILE = "#15120C", "#F7F2E8", "#FFCC33", "#0D0C0B"
TILT = -4                                                          # стрічка трохи навскіс, як у шапці


def text_path(font, text, size, cx, baseline, deg=0, pivot=(512, 512)):
    """Контур рядка: по центру cx, на базовій лінії baseline, повернутий на deg навколо pivot."""
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    s, names = size / upm, [cmap[ord(c)] for c in text]
    x = cx - sum(gs[n].width for n in names) * s / 2
    c, r, (px, py), pen = math.cos(math.radians(deg)), math.sin(math.radians(deg)), pivot, SVGPathPen(gs)
    for n in names:                                                # масштаб, віддзеркалення осі y, зсув і поворот — одною матрицею
        tx, ty = x, baseline
        gs[n].draw(TransformPen(pen, (c * s, r * s, r * s, -c * s, c * (tx - px) - r * (ty - py) + px, r * (tx - px) + c * (ty - py) + py)))
        x += gs[n].width * s
    return pen.getCommands()


def tape_poly(cx, cy, w, h, deg):
    c, r = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + c * x - r * y, cy + r * x + c * y) for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]


def raster(parts, n):
    """Знак n×n: плитка, «RE», стрічка, «CUT» — з надвибіркою, контури за правилом ненульового обходу."""
    ss = 4; N = n * ss; k = N / 1024; img = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((40 * k, 40 * k, 984 * k, 984 * k), 210 * k, fill=TILE)
    for kind, data, col in parts:
        if kind == "poly": d.polygon([(x * k, y * k) for x, y in data], fill=col); continue
        acc = None
        for poly in polygons(data):
            if len(poly) < 3: continue
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))
            m = Image.new("1", (N, N), 0); ImageDraw.Draw(m).polygon([(x * k, y * k) for x, y in poly], fill=1)
            import numpy as np
            v = np.where(np.array(m), 1 if area > 0 else -1, 0)
            acc = v if acc is None else acc + v
        mask = Image.fromarray(((acc != 0) * 255).astype("uint8"))
        img.paste(Image.new("RGBA", (N, N), col), (0, 0), mask)
    return img.resize((n, n), Image.LANCZOS)


def main(ttf, out_dir, ico):
    font, out = TTFont(ttf), Path(out_dir)
    re_ = text_path(font, "RE", 430, 512, 478)
    cut = text_path(font, "CUT", 300, 512, 790, TILT, (512, 690))
    tape = tape_poly(512, 690, 830, 280, TILT)
    parts = [("path", re_, PAPER), ("poly", tape, TAPE), ("path", cut, INK)]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect x="40" y="40" width="944" height="944" rx="210" fill="{TILE}"/>'
           f'<path d="{re_}" fill="{PAPER}"/><polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in tape)}" fill="{TAPE}"/><path d="{cut}" fill="{INK}"/></svg>')
    (out / "logo.svg").write_text(svg, "utf-8")
    big = raster(parts, 1024); big.save(out / "logo-1024.png")
    small = [("poly", tape_poly(512, 540, 940, 520, TILT), TAPE), ("path", text_path(font, "CUT", 430, 512, 690, TILT, (512, 540)), INK)]   # дрібно два рядки не читаються — лише стрічка «CUT»
    pick = lambda s: raster(small if s <= 48 else parts, s)
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    imgs = {s: pick(s) for s in sizes}
    app = Path(__file__).resolve().parent.parent / "app"           # значок вікна: Edge у режимі застосунку бере для вікна й панелі задач лише растр
    for s in (32, 256): imgs[s].save(app / f"icon-{s}.png")
    for path in (ico, app / "favicon.ico"):                         # кожен розмір намальований під себе, Windows не розтягує 32 px
        imgs[256].save(path, sizes=[(s, s) for s in sizes], append_images=[imgs[s] for s in sizes if s != 256])
    strip = Image.new("RGBA", (256 + 128 + 64 + 48 + 32 + 24 + 16 + 90, 260), (40, 40, 46, 255)); x = 10
    for s in (256, 128, 64, 48, 32, 24, 16): strip.alpha_composite(imgs[s], (x, 2)); x += s + 10
    strip.save(out / "sizes.png")
    print("svg", len(svg), "bytes")


if __name__ == "__main__": main(*sys.argv[1:4])
