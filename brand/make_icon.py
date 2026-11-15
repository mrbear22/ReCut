"""Знак ShortsMaker: широкий кадр джерела -> вертикальний жовтий шорт із «плей»."""
import sys
from PIL import Image, ImageDraw, ImageFilter
N = 1024; S = 4                                      # малюємо вчетверо більше — гладкі краї
def canvas(): return Image.new("RGBA", (N * S, N * S), (0, 0, 0, 0))
k = lambda *v: [x * S for x in v]
bg = canvas(); d = ImageDraw.Draw(bg)
d.rounded_rectangle(k(40, 40, 984, 984), 230 * S, fill=(22, 22, 28))            # плитка
g = canvas(); ImageDraw.Draw(g).ellipse(k(-200, -260, 820, 620), fill=(255, 204, 51, 46)); bg.alpha_composite(g.filter(ImageFilter.GaussianBlur(120 * S)))
m = Image.new("L", bg.size, 0); ImageDraw.Draw(m).rounded_rectangle(k(40, 40, 984, 984), 230 * S, fill=255)
bg.putalpha(Image.composite(bg.getchannel("A"), m, m))
src = canvas(); ImageDraw.Draw(src).rounded_rectangle(k(150, 330, 874, 694), 54 * S, outline=(255, 255, 255, 70), width=26 * S)   # кадр джерела 16:9
bg.alpha_composite(src)
short = canvas(); sd = ImageDraw.Draw(short)                                    # вертикальний шорт 9:16
sd.rounded_rectangle(k(352, 192, 672, 760), 64 * S, fill=(255, 204, 51))
sd.polygon(k(470, 382, 470, 570, 618, 476), fill=(22, 22, 28))
sh = canvas(); ImageDraw.Draw(sh).rounded_rectangle(k(352, 222, 672, 790), 64 * S, fill=(0, 0, 0, 150))
bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26 * S)).rotate(-8, center=(512 * S, 476 * S), resample=Image.BICUBIC))
bg.alpha_composite(short.rotate(-8, center=(512 * S, 476 * S), resample=Image.BICUBIC))
ImageDraw.Draw(bg).rounded_rectangle(k(312, 838, 712, 870), 16 * S, fill=(255, 204, 51))   # смуга таймлайну
ImageDraw.Draw(bg).rounded_rectangle(k(312, 838, 470, 870), 16 * S, fill=(255, 255, 255))
img = bg.resize((N, N), Image.LANCZOS)
img.save(sys.argv[1] + "/logo_1024.png")
img.save(sys.argv[2], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
strip = Image.new("RGBA", (256 + 128 + 64 + 48 + 32 + 16 + 70, 260), (40, 40, 46, 255)); x = 10
for s in (256, 128, 64, 48, 32, 16): strip.alpha_composite(img.resize((s, s), Image.LANCZOS), (x, 2)); x += s + 10
strip.save(sys.argv[1] + "/sizes.png")
