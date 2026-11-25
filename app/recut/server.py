"""HTTP-сервер інтерфейсу: файли сторінки, маршрути API (api.ROUTES) і запуск програми."""
import json, os, re, sys, threading, time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .api import ROUTES, Reply
from .core import Cancelled, CFG, CFG_FILE, DATA, HERE, HttpError, rd, TASK
from .fonts import scan_fonts
from .media import prepare_ffmpeg
from .publishing import media_janitor
from .system import WINDOWS, open_window, reopen_window, stop_old_server, watch_window, watchdog, window_icon
from .twitch import hls_js, hls_serve
from .update import check_update

JS, CSS = "text/javascript; charset=utf-8", "text/css; charset=utf-8"
MIME = {".mp4": "video/mp4", ".mov": "video/mp4", ".webm": "video/webm", ".m4a": "audio/mp4", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2", ".css": CSS, ".js": JS}
PAGE = {"/": ("ui.html", "text/html; charset=utf-8"), "/publish.js": ("publish.js", JS), "/styles.css": ("styles.css", CSS),
        "/icon-32.png": ("icon-32.png", "image/png"), "/icon-256.png": ("icon-256.png", "image/png"), "/favicon.ico": ("favicon.ico", "image/x-icon")}

def page_file(path):
    """Файл сторінки за адресою: (байти, тип) або None. Шрифти бренду — лише з теки fonts, без шляхів назовні."""
    if path in PAGE: name, ctype = PAGE[path]; return (HERE / name).read_bytes(), ctype
    if path == "/i18n.js":                                         # мова з налаштувань, словники мов (lang/*.js) і рушій — одним файлом
        return b"\n".join([f"const SAVED_LANG = {json.dumps(CFG.get('lang', ''))}, LANGS = {{}};".encode(), *(f.read_bytes() for f in sorted((HERE / "lang").glob("*.js"))), (HERE / "i18n.js").read_bytes()]), JS
    if path == "/hls.js": return hls_js(), JS
    if path.startswith("/js/") and re.fullmatch(r"[\w-]+\.js", name := path[4:]) and (HERE / "js" / name).is_file(): return (HERE / "js" / name).read_bytes(), JS
    if path.startswith("/fonts/") and re.fullmatch(r"[\w.-]+\.(woff2|css)", name := path[7:]) and (HERE / "fonts" / name).is_file():
        return (HERE / "fonts" / name).read_bytes(), MIME[Path(name).suffix]
    return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def send_file(self, path):
        """Файл з диска; Range — щоб відео в плеєрі перемотувалось."""
        if not path or not Path(path).is_file(): return self.reply({"error": "нема файлу"}, code=404)
        size = os.path.getsize(path); m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        a, b = (int(m[1] or 0), int(m[2]) if m[2] else size - 1) if m else (0, size - 1)
        self.send_response(206 if m else 200); self.send_header("Content-Type", MIME.get(Path(path).suffix.lower(), "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", b - a + 1)
        if m: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(a); left = b - a + 1
                while left > 0 and (chunk := f.read(min(1 << 20, left))): self.wfile.write(chunk); left -= len(chunk)
        except OSError: pass                                       # плеєр перемотав — з'єднання закрив

    def answer(self, out):
        if isinstance(out, Reply): return self.send_file(out.file) if out.file is not None else self.reply(out.body, out.ctype)
        self.reply(out)

    def call(self, method, path, args):
        """Маршрут API: відповідь — що повернув; скасували — не помилка; HttpError — свій код; решта — 500 з текстом для інтерфейсу."""
        fn = ROUTES.get((method, path))
        if not fn: return self.reply({"error": "404"}, code=404)
        try: self.answer(fn(args))
        except Cancelled: self.reply({"aborted": True})
        except HttpError as e: self.reply({"error": str(e)}, code=e.code)
        except Exception as e: self.reply({"error": str(e)}, code=500)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/hls": return hls_serve(self, q["u"])     # прев'ю запису Twitch — потоком у цю ж відповідь
            if f := page_file(u.path): return self.reply(*f)
        except ConnectionError: return                                # сторінка закрила з'єднання (перемотування, перезавантаження) — відповідати нікому
        except Exception as e: return self.reply({"error": str(e)}, code=500)
        self.call("GET", u.path, q)

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        TASK.begin(d.get("task"))                                  # потік обслуговує й інші запити: ключ задаємо щоразу
        try: self.call("POST", urlparse(self.path).path, d)
        finally:
            if TASK.current: TASK.finish(TASK.current)   # операція скінчилась — рядок поступу зникає

class Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"    # на Windows SO_REUSEADDR дає зайняти чужий порт: новий запуск «стартував», а відповідав старий

def bind(tries=1):
    for i in range(tries):
        try: return Server(("127.0.0.1", CFG["port"]), Handler)
        except OSError: time.sleep(.25 * (i < tries - 1))
    return None

def clean_preview_cache():
    """Шматки прев'ю Twitch, старші за 3 дні, і недокачані — геть: більше не знадобляться."""
    for f in (DATA / "hls").glob("*.*"):
        try:
            if f.suffix in (".part", ".m3u8") or time.time() - f.stat().st_mtime > 3 * 86400: f.unlink(missing_ok=True)
        except OSError: pass                                       # файл тримає інша програма — приберемо наступного разу

def background(*fns):
    for fn, *args in fns: threading.Thread(target=fn, args=args, daemon=True).start()

def main():
    CFG.update(rd(CFG_FILE, {})); CFG.pop("defaults", None); CFG.pop("canvas", None)   # старі версії переносили елементи й полотно в новий проєкт
    clean_preview_cache()
    url = f"http://127.0.0.1:{CFG['port']}"
    srv = bind(tries=40) if "--restart" in sys.argv else bind() or (stop_old_server(url) and bind(tries=20))   # після оновлення стара версія сама звільняє порт
    if not srv: return open_window(url)                           # вже запущено (та сама версія або рендерить) — просто відкрити вікно
    print(datetime.now(), "start", url)
    background((scan_fonts,), (prepare_ffmpeg,), (check_update,), (media_janitor,))   # перший запуск: ffmpeg качається, поки відкривається вікно
    if "--no-window" in sys.argv: WINDOWS.tied = False                # сервер без свого вікна (розробка, тести): закриті сторінки його не зупиняють
    else:
        background((watchdog,), *([(window_icon,)] if os.name == "nt" else []))
        if "--restart" in sys.argv: background((reopen_window, url))  # після оновлення: старе вікно перезавантажиться саме
        elif w := open_window(url): background((watch_window, w))
    srv.serve_forever()
