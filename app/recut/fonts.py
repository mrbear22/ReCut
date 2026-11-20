"""Системні шрифти для елементів і субтитрів."""
import os, threading
from pathlib import Path
from PIL import ImageFont

# ── системні шрифти ──
FONTS, _fonts_ready = {}, threading.Event()
def scan_fonts():
    dirs = [Path(os.environ.get("WINDIR", "C:/Windows"), "Fonts"), Path(os.environ.get("LOCALAPPDATA", "~"), "Microsoft/Windows/Fonts"),
            Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts", Path("/Library/Fonts")]
    found = {}
    for d in dirs:
        if not d.is_dir(): continue
        for f in d.rglob("*"):
            if f.suffix.lower() not in (".ttf", ".otf", ".ttc"): continue
            try:
                fam, sty = ImageFont.truetype(str(f), 12).getname()
                found.setdefault(fam if sty in ("Regular", "Normal", "") else f"{fam} {sty}", str(f))
            except Exception: pass
    FONTS.update(sorted(found.items(), key=lambda kv: kv[0].lower())); _fonts_ready.set()

def pick_font(name):
    """(назва, файл) шрифту або першого в системі."""
    _fonts_ready.wait(30)
    if name in FONTS: return name, FONTS[name]
    if not FONTS: raise RuntimeError("Не знайдено жодного шрифту в системі")
    return next(iter(FONTS.items()))
