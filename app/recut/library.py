"""Бібліотека вільних матеріалів для шортів: анімовані емодзі Noto (Google, CC BY 4.0) і звуки (CC0: Kenney та інші автори з OpenGameArt).
У збірку програми не входять: качаються при першому використанні в data/lib. Обидві ліцензії дозволяють комерційне поширення
у складі програми; CC BY вимагає згадати автора — див. CREDITS.md."""
import json, re, shutil, zipfile
from pathlib import Path
from .core import DATA
from .net import fetch, KeyedLocks

LIB = DATA / "lib"
EMOJI_LIST = "https://googlefonts.github.io/noto-emoji-animation/data/api.json"
EMOJI_GIF = "https://fonts.gstatic.com/s/e/notoemoji/latest/{}/512.gif"     # GIF, а не WebP: анімований WebP ffmpeg не декодує
OGA = "https://opengameart.org/sites/default/files/"
PACKS = [                                                          # (id, назва, автор, архів на OpenGameArt) — усі CC0
    ("jingles", "Джингли: перемога, провал", "Kenney", "jingleSounds_Kenney.zip"),
    ("swish", "Свисти й «вуш»", "artisticdude", "swishes.zip"),
    ("impact", "Удари, падіння, розбите", "rubberduck", "sfx_breaking_and_falling.zip"),
    ("voice", "Голос: «Game over», «You win»…", "Kenney", "Voiceover%20Pack.zip"),
    ("fighter", "Голос: вигуки бійця", "Kenney", "kenney_voiceoverFighter.zip"),
    ("interface", "Кліки, підтвердження, помилки", "Kenney", "kenney_interfaceSounds.zip"),
    ("ui", "Кнопки й перемикачі", "Kenney", "UI_SFX_Set.zip"),
    ("ding", "Дзвони", "StarNinjas", "ding_-_starninjas.zip"),
    ("digital", "Цифрові: лазери, бонуси", "Kenney", "Digital_SFX_Set.zip"),
    ("rpg", "Кроки, двері, монети", "Kenney", "RPGsounds_Kenney.zip"),
    ("casino", "Карти, фішки, кості", "Kenney", "kenney_casino-audio.zip"),
    ("scifi", "Sci-fi", "Kenney", "sci-fi_sounds.zip"),
]
AUDIO = (".ogg", ".mp3", ".wav")                                   # той самий звук у кількох форматах — беремо перший з цього списку
LOCKS = KeyedLocks()

def emoji_list():
    """[{c: кодова точка, t: назви й теги, g: категорія}] — список Google, кешований на диску."""
    f = LIB / "emoji.json"
    with LOCKS(f):
        if not f.is_file():
            LIB.mkdir(parents=True, exist_ok=True)
            icons = fetch(EMOJI_LIST)["icons"]
            f.write_text(json.dumps([dict(c=i["codepoint"], t=" ".join(i.get("tags", [])).replace(":", " ").strip(), g=(i.get("categories") or [""])[0])
                                     for i in icons], ensure_ascii=False), "utf-8")
    return json.loads(f.read_text("utf-8"))

def emoji(code):
    """Анімований GIF емодзі на диску; качаємо раз."""
    if not re.fullmatch(r"[0-9a-f_]{2,60}", code): raise ValueError("Невідоме емодзі")
    dst = LIB / "emoji" / f"{code}.gif"
    with LOCKS(dst):
        if not dst.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True); part = dst.with_suffix(".part"); fetch(EMOJI_GIF.format(code), part); part.replace(dst)
    return str(dst)

def sound_packs(): return [dict(id=i, name=n, by=a) for i, n, a, _ in PACKS]

def sound_pack(pid):
    """Звуки паку [{name, path}]: перший раз качаємо архів і беремо з нього лише звукові файли (без тек архіву)."""
    p = next((x for x in PACKS if x[0] == pid), None)
    if not p: raise ValueError("Невідомий пак звуків")
    d = LIB / "sfx" / pid
    with LOCKS(d):
        if not d.is_dir():
            d.parent.mkdir(parents=True, exist_ok=True); arc, part = d.with_suffix(".zip"), d.with_suffix(".part")
            fetch(OGA + p[3], arc); shutil.rmtree(part, ignore_errors=True); part.mkdir()
            with zipfile.ZipFile(arc) as z:
                files = sorted((m for m in z.infolist() if not m.is_dir() and Path(m.filename).suffix.lower() in AUDIO and not Path(m.filename).name.startswith(".")),
                               key=lambda m: AUDIO.index(Path(m.filename).suffix.lower()))
                seen = set()
                for m in files:
                    stem = re.sub(r'[<>:"/\\|?*]+', "_", Path(m.filename).stem)
                    if stem.lower() in seen: continue
                    seen.add(stem.lower())
                    with z.open(m) as src, open(part / (stem + Path(m.filename).suffix.lower()), "wb") as out: shutil.copyfileobj(src, out)
            part.rename(d); arc.unlink(missing_ok=True)
    natural = lambda f: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", f.name.lower())]   # swish-2 перед swish-10
    return [dict(name=f.stem.replace("_", " "), path=str(f)) for f in sorted(d.iterdir(), key=natural) if f.suffix.lower() in AUDIO]
