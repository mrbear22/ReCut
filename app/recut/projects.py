"""Проєкти: кожен — окремий JSON; обкладинка."""
import json, re, time, uuid
from pathlib import Path
from .core import CANVAS, CFG, is_url, LOCK, MIXES, PROJ, run, save_cfg, THUMBS
from .media import ffbin, ffmpeg_ready, probe

# ── проєкти: кожен — окремий файл; новий — з типовими елементами (інші — лише імпортом) ──
def proj_file(pid):
    if not re.fullmatch(r"[0-9a-f]{10}", str(pid)): raise ValueError("Невідомий проєкт")
    return PROJ / f"{pid}.json"

def load_project(pid): return json.loads(proj_file(pid).read_text("utf-8"))

def write_project(p):
    p["updated"] = time.time(); proj_file(p["id"]).write_text(json.dumps(p, ensure_ascii=False, indent=1), "utf-8"); return p

def update_project(pid, fn):
    with LOCK: p = load_project(pid); fn(p); return write_project(p)

def new_project(**kw):
    now = time.time()
    p = dict(id=uuid.uuid4().hex[:10], name="", created=now, video="", region=None, clips=[],
             elements=[], canvas=list(CANVAS), cues=[], renders=[])            # елементи з інших проєктів — лише імпортом
    with LOCK: return write_project({**p, **kw})

def delete_project(pid):
    """Проєкт геть; відео й готові шорти на диску лишаються."""
    for r in load_project(pid)["renders"]:
        for f in r["files"]: Path(f["thumb"]).unlink(missing_ok=True)
    proj_file(pid).unlink(); (THUMBS / f"cover_{pid}.jpg").unlink(missing_ok=True)
    if CFG["project"] == pid: CFG["project"] = ""; save_cfg()

def projects():
    return sorted((json.loads(f.read_text("utf-8")) for f in PROJ.glob("*.json")), key=lambda p: -p["updated"])

def cover(pid):
    """Обкладинка проєкту з власного відео: кадр на третині, один раз."""
    f = THUMBS / f"cover_{pid}.jpg"
    if not f.is_file() and not ffmpeg_ready(): return ""             # ffmpeg ще качається: картинки головної не чекають його й не займають усі з'єднання сторінки
    if not f.is_file():
        p = load_project(pid); v = p.get("video", "")
        if not v or is_url(v) or not Path(v).is_file(): return ""
        run([ffbin("ffmpeg"), "-y", "-v", "error", "-ss", f"{probe(v)[2] * .3:.1f}", "-i", v, "-frames:v", "1", "-vf", "scale=480:-2", str(f)])
    return str(f) if f.is_file() else ""

def listing():
    """Проєкти для головної: у готових шортах позначено, чи файл ще на диску."""
    ps = projects()
    for f in (f for p in ps for r in p["renders"] for f in r["files"]): f["exists"] = Path(f["path"]).is_file()
    return ps

def project_files(picked):
    """Файли, які інтерфейс може відкрити (/file) чи показати в теці: обрані користувачем, проєктів, рендерів, копій для перегляду."""
    s = set(picked) | {str(p) for p in MIXES.glob("*.m4a")} | {str(p) for p in MIXES.glob("*.mp4")}
    for p in projects():
        s |= {p["video"]} | {e[k] for e in p["elements"] for k in ("preview", "logo", "path") if e.get(k)} | {m["path"] for m in p.get("music", [])}
        s |= {r["out"] for r in p["renders"]} | {f[k] for r in p["renders"] for f in r["files"] for k in ("path", "thumb")}
    return s
