"""Маршрути HTTP API інтерфейсу: кожен — коротка функція, вся робота — у своїх модулях.
Функція отримує параметри запиту (GET — рядок запиту, POST — JSON) і повертає відповідь як дані (JSON) або Reply."""
import base64, io, threading, webbrowser
from datetime import datetime
from . import brands, library
from .analysis import AI, analyze
from .art import art
from .camera import detect_cam
from .core import CFG, CODE_VERSION, HttpError, is_url, PAD, PICKED, save_cfg, TASK
from .fonts import FONTS, _fonts_ready
from .media import duration, ffmpeg_ready, peaks, preview_mix, preview_video, probe
from .projects import cover, delete_project, listing, load_project, new_project, project_files, update_project
from .publishing import BUFFER, publish_batch, save_post, unqueue
from .render import JOB, render_dir, start as start_render
from .storage import clear_store, storage
from .stt import realign, subtitles
from .system import LINKS, WINDOWS, ask_dir, ask_file, finish_update, quit_app, reveal
from .twitch import TW_PENDING, check_vod, preview_progress, status as twitch_status, tw_login, tw_logout, twitch_videos, vod
from .update import UPDATE, VERSION, apply_update

ROUTES = {}                                                        # (метод, шлях) -> функція(параметри)

def route(method, path):
    def add(fn): ROUTES[method, path] = fn; return fn
    return add
get = lambda path: route("GET", path)
post = lambda path: route("POST", path)

class Reply:
    """Відповідь не-JSON: байти з типом, або файл з диска (з підтримкою Range для відео)."""
    def __init__(self, body=None, ctype="application/json", file=None): self.body, self.ctype, self.file = body, ctype, file

# ── стан програми ──
@get("/api/state")
def state(q): return dict(cfg=CFG, job=JOB)

@get("/api/status")
def job_status(q): return dict(JOB, tasks=TASK.rows, ffmpeg=ffmpeg_ready())

@get("/api/version")
def version(q): return dict(version=CODE_VERSION, app=VERSION, boot=WINDOWS.started)

@get("/api/update")
def update_available(q): return dict(current=VERSION, version=UPDATE.get("version"))

@post("/api/update/apply")
def update_apply(d):
    setup = apply_update(); threading.Thread(target=finish_update, args=(setup,), daemon=True).start()
    return dict(kind="full" if setup else "app")

@post("/api/config")
def config(d):
    CFG.update({k: v for k, v in d.items() if k in CFG and k != "project"}); save_cfg(); return CFG

@post("/api/log")
def page_error(d):
    """Помилка сторінки — у журнал програми: так видно, чому вікно відкрилось порожнім."""
    print(datetime.now(), "page:", str(d.get("text", ""))[:2000]); return {}

@post("/api/cancel")
def cancel(d): TASK.cancel(d["key"]); return {}

# ── вікна ──
@post("/api/ping")
def ping(d): WINDOWS.ping(d.get("page", "?")); return {}

@post("/api/bye")
def bye(d):
    """Вікно закрили: останнє — програма виходить одразу."""
    if WINDOWS.bye(d.get("page", "?")): threading.Thread(target=quit_app, daemon=True).start()
    return {}

@post("/api/open")
def open_link(d):
    """Лише відомі адреси: сторінка не може відкрити довільне посилання."""
    if url := LINKS.get(d.get("link")): webbrowser.open(url)
    elif d.get("link") == "twitch_activate" and str(TW_PENDING.get("uri", "")).startswith("https://www.twitch.tv/"): webbrowser.open(TW_PENDING["uri"])
    return {}

# ── файли й діалоги ──
@post("/api/pick")
def pick(d):
    if f := ask_file(d["kind"]): PICKED.add(f)
    return dict(path=f)

@post("/api/pick_dir")
def pick_dir(d): return dict(path=ask_dir(render_dir(load_project(d["id"]))))

@get("/file")
def file(q): return Reply(file=q.get("p") if q.get("p") in project_files(PICKED) else "")

@post("/api/reveal")
def reveal_file(d):
    if d["path"] not in project_files(PICKED): raise HttpError(403, "заборонено")
    reveal(d["path"]); return {}

@get("/api/fonts")
def fonts(q): _fonts_ready.wait(30); return list(FONTS)

@get("/api/brands")
def brand_list(q): return {k: dict(name=n, color=c, path=p) for k, (n, c, p) in brands.BRANDS.items()}

# ── відео ──
@get("/api/probe")
def probe_video(q):
    src = q["p"]; sw, sh, dur, na = probe(src)
    return dict(sw=sw, sh=sh, dur=dur, tracks=na, mix=preview_mix(src, na), play=preview_video(src), hls=is_url(src), title=vod(src)["title"] if is_url(src) else "")

@get("/api/audio")
def audio_length(q): return dict(dur=duration(q["p"]))

@get("/api/peaks")
def audio_peaks(q): return peaks(q["p"], int(q["track"]) if q.get("track") else None)

@post("/api/detect_cam")
def find_cam(d): return dict(rect=detect_cam(d["frames"]))

@post("/api/analyze")
def find_moments(d): return analyze(d["video"], d.get("region"), d.get("suggest", True), d.get("lang", ""))

@post("/api/subs")
def make_subtitles(d): return subtitles(d["video"], d.get("spans") or [d["region"]], d.get("lang", ""), d.get("words", 3))

@post("/api/realign")
def realign_cue(d): return dict(k=realign(d["video"], float(d["a"]), float(d["b"]), d["text"], d.get("lang", "")))

# ── бібліотека: анімовані емодзі й звуки (качаються при першому використанні) ──
@get("/api/lib/emoji")
def lib_emoji(q): return library.emoji_list()

@post("/api/lib/emoji")
def lib_emoji_file(d): p = library.emoji(d["code"]); PICKED.add(p); return dict(path=p)

@get("/api/lib/sounds")
def lib_sounds(q): return library.sound_packs()

@post("/api/lib/sounds")
def lib_sound_pack(d):
    out = library.sound_pack(d["id"]); PICKED.update(s["path"] for s in out); return out   # прослухати й додати

@post("/api/element")
def element_image(d):
    img, w, h = art(d); buf = io.BytesIO(); img.save(buf, "PNG")
    return dict(w=w, h=h, pad=PAD, img="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())

@post("/api/render")
def render(d): return start_render(d["id"], d["clips"], d["elements"], d["cues"], d.get("music", []), d.get("out"), d.get("task"))

# ── проєкти ──
@get("/api/projects")
def projects(q): return listing()

@get("/api/project")
def project(q): return load_project(q["id"])

@get("/api/cover")
def project_cover(q): return Reply(file=cover(q["id"]))

@post("/api/project/new")
def project_new(d):
    pr = new_project(**{k: d[k] for k in ("video", "name", "cover") if d.get(k)}); CFG["project"] = pr["id"]; save_cfg(); return pr

@post("/api/project/open")
def project_open(d): load_project(d["id"]); CFG["project"] = d["id"]; save_cfg(); return {}

@post("/api/project/save")
def project_save(d):
    keys = ("name", "video", "region", "clips", "elements", "cues", "scan", "music", "canvas", "cover")
    return dict(updated=update_project(d["id"], lambda pr: pr.update({k: d[k] for k in keys if k in d}))["updated"])

@post("/api/project/delete")
def project_delete(d): delete_project(d["id"]); return {}

@get("/api/storage")
def disk_space(q): return storage()

@post("/api/storage/clear")
def disk_clear(d): return clear_store(d["key"])

# ── Twitch ──
@get("/api/twitch")
def twitch(q): return twitch_status()

@get("/api/twitch/videos")
def twitch_list(q): return twitch_videos(q.get("channel", ""))

@post("/api/twitch/login")
def twitch_login(d): return tw_login()

@post("/api/twitch/logout")
def twitch_logout(d): tw_logout(); return {}

@post("/api/vod")
def twitch_vod(d): return check_vod(d["url"])

@get("/api/hls/progress")
def buffering(q): return preview_progress()

# ── публікація й ШІ ──
@get("/api/ai")
def ai(q): return dict(model=AI.model(), setup=AI.setup_state, can_setup=AI.can_setup(), size_gb=5)

@post("/api/ai/setup")
def ai_setup(d): AI.begin_setup(); return AI.setup_state

@get("/api/buffer")
def buffer(q): return dict(connected=True, channels=BUFFER.channels()) if BUFFER.key else dict(connected=False)

@get("/api/buffer/queue")
def buffer_queue(q): return dict(posts=BUFFER.scheduled())

@post("/api/buffer/key")
def buffer_key(d): BUFFER.set_key(d.get("key", "")); return dict(connected=bool(BUFFER.key))

@post("/api/post/save")
def post_save(d): save_post(d["id"], d["path"], d["post"]); return {}

@post("/api/post/unqueue")
def post_unqueue(d): return unqueue(d["id"], d["path"])

@post("/api/publish")
def publish(d): return publish_batch(d["id"], d["plan"], d.get("privacy", "public"), int(d.get("limit") or 0))
