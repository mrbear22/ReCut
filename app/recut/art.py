"""Елементи-картинки: плашки, текст, чат, соцмережі, зображення."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from . import brands
from .core import PAD, ev
from .fonts import pick_font

# ── елементи-картинки: плашки, текст, зображення ──
def wrap(text, font, w):
    lines = [""]
    for word in text.split():
        t = (lines[-1] + " " + word).strip()
        if font.getlength(t) <= w or not lines[-1]: lines[-1] = t
        else: lines.append(word)
    return lines

def fit_lines(text, font, size, w, max_lines, min_size=14):
    while True:
        f = ImageFont.truetype(font, size); lines = wrap(text, f, w) if text else []
        if not lines or len(lines) <= max_lines and max(map(f.getlength, lines)) <= w or size <= min_size: return f, lines, size
        size -= 2

def round_img(img, size, radius):
    img = img.convert("RGB"); r = max(size[0] / img.width, size[1] / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    l, t = (img.width - size[0]) // 2, (img.height - size[1]) // 2
    m = Image.new("L", size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, *size), radius, fill=255)
    return img.crop((l, t, l + size[0], t + size[1])), m

def avatar(path, a):
    if not path or not Path(path).is_file(): return None
    lg = Image.open(path).convert("RGBA"); pixel = lg.getcolors(64) is not None   # піксель-арт — без згладжування
    lg = lg.resize((a, a), Image.NEAREST if pixel else Image.LANCZOS)
    mk = Image.new("L", (a, a), 0); ImageDraw.Draw(mk).ellipse((0, 0, a - 1, a - 1), fill=255)
    return lg, mk

def stream_card(g, k, font):
    """Плашка етеру: аватар у червоному колі з бейджем LIVE, нік, назва, категорія."""
    cw, pad, av, gap = k(968), k(28), k(128), k(26); tx = cw - 2 * pad - av - gap
    nf, nl, _ = fit_lines(g("channel"), font, k(42), tx, 1)
    tf, tl, ts = fit_lines(g("title"), font, k(32), tx, 2)
    cf, cl, _ = fit_lines(g("category"), font, k(28), tx, 1)
    blocks = [(nf, nl, (255, 255, 255), k(42) * 1.3), (tf, tl, (222, 222, 227), ts * 1.3), (cf, cl, (191, 148, 255), k(28) * 1.4)]
    text_h = int(sum(len(l) * lh for _, l, _, lh in blocks)); ch = max(av + k(22), text_h) + 2 * pad
    img, d = panel(cw, ch, k(18), (24, 24, 27))
    ax, ay = PAD + pad, PAD + (ch - av - k(10)) // 2
    d.ellipse((ax - k(5), ay - k(5), ax + av + k(5), ay + av + k(5)), fill=(233, 25, 22))
    if a := avatar(g("logo"), av): img.paste(a[0], (ax, ay), a[1])
    else: d.ellipse((ax, ay, ax + av, ay + av), fill=(60, 60, 66))
    if g("badge"):
        bf = ImageFont.truetype(font, k(24)); bw = int(bf.getlength(g("badge"))) + k(18); bh = k(34)
        bx, by = ax + (av - bw) // 2, ay + av - bh // 2 + k(4)
        d.rounded_rectangle((bx, by, bx + bw, by + bh), k(6), fill=(233, 25, 22))
        d.text((bx + bw / 2, by + bh / 2), g("badge"), font=bf, fill="white", anchor="mm")
    x, y = ax + av + gap, PAD + (ch - text_h) // 2
    for f, lines, col, lh in blocks:
        for l in lines: d.text((x, y), l, font=f, fill=col); y += int(lh)
    return img, cw, ch

def video_card(g, k, font):
    """Плашка відео: прев'ю 16:9, назва до трьох рядків, канал з аватаром."""
    cw, pad, th = k(968), k(28), k(200); tw = th * 16 // 9; tx = cw - 3 * pad - tw
    tf, lines, size = fit_lines(g("title"), font, k(44), tx, 3, k(20))
    cf = ImageFont.truetype(font, k(32)); lh = int(size * 1.3)
    text_h = lh * len(lines) + (int(k(32) * 1.6) if g("channel") else 0); ch = max(th, text_h) + 2 * pad
    img, d = panel(cw, ch, k(44), "white")
    src = Image.open(g("preview")) if Path(g("preview") or "-").is_file() else Image.new("RGB", (16, 9), (205, 205, 210))
    t, m = round_img(src, (tw, th), k(18)); tx0 = PAD + pad; img.paste(t, (tx0, PAD + (ch - th) // 2), m)
    x, y = tx0 + tw + pad, PAD + (ch - text_h) // 2
    for l in lines: d.text((x, y), l, font=tf, fill=(15, 15, 15)); y += lh
    if g("channel"):
        y += int(k(32) * 0.3)
        if a := avatar(g("logo"), int(k(32) * 1.4)): img.paste(a[0], (x, y + (k(32) - a[0].width) // 2 + k(4)), a[1]); x += a[0].width + k(14)
        d.text((x, y), g("channel"), font=cf, fill=(96, 96, 96))
    return img, cw, ch

def make_card(el):
    """Плашка відео чи етеру в масштабі s: (RGBA з полем PAD під тінь, ширина, висота)."""
    s = float(el.get("s", 1.0)); k = lambda v: max(1, round(v * s))
    return (stream_card if el["type"] == "stream" else video_card)(lambda n: el.get(n) or "", k, pick_font(el.get("font"))[1])

def make_text(el):
    """Текст: з плашкою-фоном (заклик, нікнейм, LIVE) або з обведенням просто поверх відео."""
    f = ImageFont.truetype(pick_font(el.get("font"))[1], max(8, round(float(el.get("size", 72)))))
    lines = (el.get("text") or " ").split("\n"); lh = round(f.size * 1.25)
    ink = [f.getbbox(l or " ", anchor="ls") for l in lines]          # видимі межі гліфів: у піксельних шрифтах відступ символу ≠ малюнок
    widths = [x1 - x0 for x0, _, x1, _ in ink]; tw = max(widths)
    bg = el.get("bgOn"); px, py = (round(f.size * .5), round(f.size * .25)) if bg else (0, 0); stroke = 0 if bg else max(1, f.size // 12)
    cw, ch = round(tw) + 2 * px + 2 * stroke, lh * len(lines) + 2 * py
    img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    if bg:                                                        # фон по контуру рядків, як у TikTok: кожен рядок — своєї ширини
        shape = text_shape(img.size, widths, px, py, lh, round(f.size * .3))
        shadow_of(img, shape); img.paste(Image.new("RGBA", img.size, el.get("bg", "#000000")), (0, 0), shape)
    asc, desc = f.getmetrics()
    for i, l in enumerate(lines):                                 # центр видимого малюнка рядка — точно посередині фону
        x0, _, x1, _ = ink[i]; base = PAD + py + i * lh + lh / 2 + (asc - desc) / 2
        d.text((PAD + cw / 2 - (x0 + x1) / 2, base), l, font=f, fill=el.get("color", "#ffffff"), anchor="ls",
               stroke_width=stroke, stroke_fill=el.get("stroke") or "#000000")
    return img, cw, ch

def make_social(el):
    """Плашка соцмережі: логотип і нікнейм. Вигляд — темна плашка, плашка кольору мережі або без плашки (з обведенням)."""
    key = el.get("net") if el.get("net") in brands.BRANDS else "tiktok"; style = el.get("style", "dark")
    f = ImageFont.truetype(pick_font(el.get("font"))[1], max(8, round(float(el.get("size", 46)))))
    handle = (el.get("handle") or "").strip(); logo = round(f.size * 1.3); gap = round(f.size * .4) if handle else 0
    pad = (round(f.size * .3), round(f.size * .55)) if style != "clean" else (0, 0)      # зверху-знизу, праворуч
    stroke = 0 if style != "clean" else max(1, f.size // 12)
    cw = pad[0] + logo + gap + (round(f.getlength(handle)) + 2 * stroke if handle else 0) + (pad[1] if handle else pad[0])
    ch = logo + 2 * pad[0]
    img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); d = ImageDraw.Draw(img); r = round(ch * .32)
    name, col, _ = brands.BRANDS[key]
    if style == "dark": shadow(img, cw, ch, r); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), r, fill=(18, 18, 22, 235))
    if style == "brand":
        shadow(img, cw, ch, r); m = Image.new("L", img.size, 0); ImageDraw.Draw(m).rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), r, fill=255)
        bg = brands._gradient(max(cw, ch), brands.INSTAGRAM_GRADIENT).resize((cw, ch)) if key == "instagram" else Image.new("RGB", (cw, ch), col)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); layer.paste(bg, (PAD, PAD)); img.paste(layer, (0, 0), m)
    ink = "#000000" if style == "brand" and key == "kick" else "#ffffff"
    if style == "brand":                                          # на кольоровій плашці — білий знак без квадрата
        img.paste(Image.new("RGBA", (logo, logo), ink), (PAD + pad[0], PAD + pad[0]), brands.glyph_mask(key, logo))
    else: img.alpha_composite(brands.brand_tile(key, logo), (PAD + pad[0], PAD + pad[0]))
    if handle:
        ImageDraw.Draw(img).text((PAD + pad[0] + logo + gap + stroke, PAD + ch / 2), handle, font=f, fill=ink, anchor="lm", stroke_width=stroke, stroke_fill="black")
    return img, cw, ch

def make_image(el):
    """Логотип / стікер шириною w зі збереженням пропорцій."""
    w = max(8, round(float(el.get("w", 300))))
    src = Image.open(el["path"]).convert("RGBA") if Path(el.get("path") or "-").is_file() else Image.new("RGBA", (4, 3), (205, 205, 210, 255))
    h = max(1, round(w * src.height / src.width)); img = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0))
    img.paste(src.resize((w, h), Image.LANCZOS), (PAD, PAD)); return img, w, h

def make_chat(el):
    """Повідомлення з чату стріму: нік своїм кольором і текст на темній плашці."""
    s = float(el.get("s", 1)); k = lambda v: max(1, round(v * s)); f = ImageFont.truetype(pick_font(el.get("font"))[1], k(36))
    name, pad, lh = (el.get("name") or "").strip(), k(20), round(k(36) * 1.3)
    lines = wrap((f"{name}: " if name else "") + (el.get("text") or ""), f, k(720) - 2 * pad) or [""]
    cw, ch = round(max(map(f.getlength, lines))) + 2 * pad, lh * len(lines) + 2 * pad - (lh - k(36))
    img, d = panel(cw, ch, k(16), (20, 20, 24, 235))
    for i, l in enumerate(lines):
        x, y = PAD + pad, PAD + pad + i * lh
        if i == 0 and name and l.startswith(name + ":"):
            d.text((x, y), name + ":", font=f, fill=el.get("nameColor", "#a970ff")); x += f.getlength(name + ": "); l = l[len(name) + 1:].lstrip()
        d.text((x, y), l, font=f, fill=(240, 240, 245))
    return img, cw, ch

ART = {"card": make_card, "stream": make_card, "text": make_text, "image": make_image,   # елементи, що малюються картинкою поверх відео
       "chat": make_chat, "social": make_social}

def art(el): return ART[el["type"]](el)

def layer(l, sw, sh):
    """Кадрування шару відео: (фільтр, ширина, висота) на місці призначення."""
    x, y, w, h = l["src"]; cw_, ch_ = ev(w * sw), ev(h * sh)
    dw = ev(l["w"]); dh = ev(dw * ch_ / cw_)
    return f"crop={cw_}:{ch_}:{int(x * sw)}:{int(y * sh)},scale={dw}:{dh},setsar=1", dw, dh

def frame(l, dw, dh):
    """Форма шару відео (заокруглена, коло) і рамка: (маска або None, обвідка або None)."""
    shape, b, r = l.get("shape", "rect"), round(float(l.get("bw", 0))), round(float(l.get("radius", 40)))
    def draw(img, grow, **kw):                                   # обвідка лягає зовні шару: радіус більший на її товщину
        d, box = ImageDraw.Draw(img), (0, 0, img.width - 1, img.height - 1)
        d.ellipse(box, **kw) if shape == "circle" else d.rounded_rectangle(box, radius=r + grow if shape == "round" else 0, **kw)
    mask = ring = None
    if shape != "rect": mask = Image.new("L", (dw, dh), 0); draw(mask, 0, fill=255)
    if b: ring = Image.new("RGBA", (dw + 2 * b, dh + 2 * b), (0, 0, 0, 0)); draw(ring, b, outline=l.get("border", "#ffffff"), width=b)
    return mask, ring

def text_shape(size, widths, px, py, lh, r):
    """Маска фону тексту за контуром рядків: заокруглені кути назовні, рядки зростаються без щілин."""
    m = Image.new("L", size, 0); d = ImageDraw.Draw(m); cx, n = size[0] / 2, len(widths)
    rows = [(cx - w / 2 - px, PAD + i * lh + (0 if i == 0 else py), cx + w / 2 + px, PAD + (i + 1) * lh + py + (py if i == n - 1 else 0)) for i, w in enumerate(widths)]
    for x0, y0, x1, y1 in rows: d.rounded_rectangle((x0, y0, x1, y1), r, fill=255)
    for (a0, _, a1, ab), (b0, _, b1, _) in zip(rows, rows[1:]):  # стик рядків: без заокруглень там, де обидва рядки є
        d.rectangle((max(a0, b0), ab - r, min(a1, b1), ab + r), fill=255)
    return m

def shadow_of(img, mask):
    """М'яка тінь під фігуру будь-якої форми."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0)); sh.paste(Image.new("RGBA", img.size, (0, 0, 0, 110)), (0, 12), mask)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))

def shadow(img, cw, ch, r):
    m = Image.new("L", img.size, 0); ImageDraw.Draw(m).rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), r, fill=255); shadow_of(img, m)

def panel(cw, ch, r, fill):
    """Плашка cw×ch з тінню на прозорому полотні з полем PAD: (картинка, малювання)."""
    img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); shadow(img, cw, ch, r)
    d = ImageDraw.Draw(img); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), r, fill=fill); return img, d
