"""Записи Twitch: вхід, список записів, плейлисти й кеш шматків, прев'ю потоком."""
import json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from datetime import datetime
from pathlib import Path
import numpy as np
from .core import DATA, is_url, LIBS, rd, report, run, TASK
from .libs import need_libs, parallel
from .net import KeyedLocks, fetch, open_url, pump, retrying

# ── записи Twitch: відео не на диску; беремо лише потрібні шматки — у низькій якості для аналізу, в оригінальній для рендеру ──
HLS_JS = "https://cdn.jsdelivr.net/npm/hls.js@1.6.13/dist/hls.min.js"   # плеєр плейлистів для прев'ю
HLS_CACHE, HLS_KEEP, VOD_TTL = DATA / "hls", 2e9, 1200           # шматки для прев'ю (найстаріші — геть понад 2 ГБ); опис запису перечитуємо раз на 20 хв
VODS, VOD_LOCK = {}, threading.Lock()
HLS_LOCKS = KeyedLocks()                                          # шматок, що саме качається, — один на всіх, хто його просить

# вхід через Twitch (Device Code): користувач підтверджує код на twitch.tv/activate, пароль програма не бачить
TWITCH_CLIENT_ID = "id63h2ljfj0lh5xjp6urad01tbz8vz"             # публічний Client ID застосунку ReCut (dev.twitch.tv, тип «Public»): не секрет
TW_FILE, TW_SCOPES, TW_PENDING = DATA / "twitch.json", "user:read:broadcast", {}   # токени — окремо від налаштувань, в інтерфейс не віддаються

def tw_form(url, **form):
    req = urllib.request.Request(url, urllib.parse.urlencode(form).encode(), {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "ReCut"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        try: return dict(json.loads(e.read() or b"{}"), status=e.code)
        except ValueError: return dict(status=e.code, message=str(e))

def tw_store(t):
    """Нові токени (refresh-токен одноразовий — щоразу зберігаємо новий) і хто увійшов."""
    acc = dict(access=t["access_token"], refresh=t["refresh_token"], until=time.time() + t.get("expires_in", 3600))
    TW_FILE.write_text(json.dumps(acc), "utf-8")
    u = tw_api("users")["data"][0]; acc["user"] = dict(id=u["id"], login=u["login"], name=u["display_name"], avatar=u["profile_image_url"])
    TW_FILE.write_text(json.dumps(acc), "utf-8")

def tw_api(path, retry=True):
    acc = rd(TW_FILE, None)
    if not acc: raise RuntimeError("Не виконано вхід у Twitch")
    if time.time() > acc["until"] - 60: tw_refresh(acc); acc = rd(TW_FILE, None)
    req = urllib.request.Request("https://api.twitch.tv/helix/" + path, headers={"Authorization": "Bearer " + acc["access"], "Client-Id": TWITCH_CLIENT_ID, "User-Agent": "ReCut"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry: tw_refresh(acc); return tw_api(path, False)
        raise RuntimeError(f"Twitch відповів {e.code}") from e

def tw_refresh(acc):
    t = tw_form("https://id.twitch.tv/oauth2/token", client_id=TWITCH_CLIENT_ID, grant_type="refresh_token", refresh_token=acc["refresh"])
    if "access_token" not in t: TW_FILE.unlink(missing_ok=True); raise RuntimeError("Вхід у Twitch застарів — увійди знову")
    TW_FILE.write_text(json.dumps(dict(acc, access=t["access_token"], refresh=t["refresh_token"], until=time.time() + t.get("expires_in", 3600))), "utf-8")

def tw_login():
    """Почати вхід: код для twitch.tv/activate; токен чекаємо у фоні, поки користувач підтверджує."""
    if not TWITCH_CLIENT_ID: raise RuntimeError("Вхід через Twitch у цій версії ще не налаштований")
    d = tw_form("https://id.twitch.tv/oauth2/device", client_id=TWITCH_CLIENT_ID, scopes=TW_SCOPES)
    if "device_code" not in d: raise RuntimeError("Twitch: " + str(d.get("message", d)))
    TW_PENDING.clear(); TW_PENDING.update(code=d["user_code"], uri=d["verification_uri"], until=time.time() + d.get("expires_in", 1800), err="")
    def wait():
        while TW_PENDING.get("code") == d["user_code"] and time.time() < TW_PENDING["until"]:
            time.sleep(max(2, d.get("interval", 5)))
            t = tw_form("https://id.twitch.tv/oauth2/token", client_id=TWITCH_CLIENT_ID, scopes=TW_SCOPES, device_code=d["device_code"],
                        grant_type="urn:ietf:params:oauth:grant-type:device_code")
            if "access_token" in t:
                try: tw_store(t); TW_PENDING.clear()
                except Exception as e: TW_PENDING.update(code="", err=str(e))
                return
            if t.get("message") not in ("authorization_pending", "slow_down"): TW_PENDING.update(code="", err=str(t.get("message", "?"))); return
        if TW_PENDING.get("code") == d["user_code"]: TW_PENDING.update(code="", err="Код застарів — спробуй ще раз")
    threading.Thread(target=wait, daemon=True).start()
    return dict(code=d["user_code"], uri=d["verification_uri"])

def tw_logout():
    acc = rd(TW_FILE, None); TW_FILE.unlink(missing_ok=True); TW_PENDING.clear()
    if acc and TWITCH_CLIENT_ID: tw_form("https://id.twitch.tv/oauth2/revoke", client_id=TWITCH_CLIENT_ID, token=acc["access"])

def twitch_videos(channel=""):
    """Записи трансляцій: свого акаунта (після входу — з датою) або будь-якого каналу за назвою (без входу, через yt-dlp)."""
    secs = lambda s: sum(int(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in re.findall(r"(\d+)([hms])", s or ""))
    if not channel:
        acc = rd(TW_FILE, None)
        if not acc or "user" not in acc: return []
        return [dict(url=v["url"], title=v["title"], date=v["created_at"], dur=secs(v["duration"]), views=v["view_count"],
                     thumb=v["thumbnail_url"].replace("%{width}", "480").replace("%{height}", "270"))
                for v in tw_api(f"videos?user_id={acc['user']['id']}&type=archive&first=30")["data"]]
    if not re.fullmatch(r"\w{3,25}", channel): raise ValueError("Назва каналу — як у посиланні twitch.tv/назва")
    ytdlp_install()
    r = ytdlp("--flat-playlist", "-J", "--no-warnings", "--playlist-end", "30", f"https://www.twitch.tv/{channel}/videos?filter=archives&sort=time")
    if r.returncode: raise RuntimeError("Канал не знайдено або він без записів")
    return [dict(url=e["url"], title=e.get("title") or "", date="", dur=float(e.get("duration") or 0), views=e.get("view_count") or 0, thumb=e.get("thumbnail") or "")
            for e in json.loads(r.stdout).get("entries") or []]

def ytdlp(*args):
    """yt-dlp окремим процесом: оновлена версія підхоплюється без перезапуску програми."""
    exe = Path(sys.executable); py = exe.with_name("python.exe") if exe.with_name("python.exe").is_file() else exe
    return run([str(py), "-c", f"import sys; sys.path.insert(0, {str(LIBS)!r}); import yt_dlp; sys.exit(yt_dlp.main(sys.argv[1:]))", *args])

def ytdlp_install(upgrade=False):
    """Найновіший yt-dlp з PyPI, коли вперше знадобиться; Twitch щось змінив — оновлюємо."""
    if upgrade or not any(LIBS.glob("yt_dlp-*.dist-info")):
        need_libs([f"yt-dlp=={fetch('https://pypi.org/pypi/yt-dlp/json')['info']['version']}"], "yt_dlp", "Завантажую yt-dlp для Twitch, 3 МБ", "twitch")

def vod(url, fresh=False):
    """Запис Twitch: назва, тривалість і плейлисти якостей. Відео ніде не зберігається — ffmpeg і прев'ю беруть шматки за плейлистом."""
    with VOD_LOCK:
        v = VODS.get(url)
        if v and not fresh and time.time() - v["t"] < VOD_TTL: return v
        if TASK.current: report("twitch", "Відкриваю запис Twitch", None)
        ytdlp_install()
        r = ytdlp("-J", "--no-warnings", "--no-playlist", url)
        if r.returncode:                                           # стара версія вже не розуміє Twitch — оновлюємо й пробуємо ще раз
            ytdlp_install(upgrade=True); r = ytdlp("-J", "--no-warnings", "--no-playlist", url)
        if r.returncode:
            err = (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["?"])[-1].replace("ERROR: ", "")
            raise RuntimeError(f"Запис Twitch не відкривається: {err[:300]}")
        d = json.loads(r.stdout)
        fs = [f for f in d.get("formats", []) if str(f.get("protocol", "")).startswith("m3u8")]
        vids = sorted((f for f in fs if f.get("vcodec") not in (None, "none")), key=lambda f: (f.get("height") or 0, f.get("fps") or 0))
        if not vids: raise RuntimeError("У записі Twitch немає відео")
        best = vids[-1]; at = lambda h: next((f for f in vids if (f.get("height") or 0) >= h), best)["url"]
        aud = next((f["url"] for f in fs if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")), vids[0]["url"])
        v = VODS[url] = dict(t=time.time(), id=d.get("id", ""), title=d.get("title") or d.get("id", ""), dur=float(d.get("duration") or 0), w=best["width"], h=best["height"],
                             best=best["url"], view=at(720), mid=at(480), low=vids[0]["url"], audio=aud, base=best["url"].rsplit("/", 2)[0] + "/", thumb=d.get("thumbnail") or "")
        return v

def m3u8(url, to):
    """Плейлист з адресами, переписаними через to(повна адреса)."""
    to_ = lambda u: to(urllib.parse.urljoin(url, u))
    return "\n".join(re.sub(r'URI="([^"]+)"', lambda m: f'URI="{to_(m[1])}"', l) if l.startswith("#") else to_(l) if l.strip() else l
                     for l in fetch(url, raw=True).decode("utf-8").splitlines())

def hls_parts(url):
    """Плейлист → (адреса init-шматка або None, [(початок, тривалість, адреса шматка)])."""
    init, out, t, d = None, [], 0.0, 0.0
    for l in fetch(url, raw=True).decode("utf-8").splitlines():
        if l.startswith("#EXT-X-MAP:"): init = urllib.parse.urljoin(url, re.search(r'URI="([^"]+)"', l)[1])
        elif l.startswith("#EXTINF:"): d = float(l[8:].split(",")[0])
        elif l.strip() and not l.startswith("#"): out.append((t, d, urllib.parse.urljoin(url, l.strip()))); t += d
    return init, out

HLS_GOT = {}                                                       # шматки, що качаються зараз: (байтів отримано, розмір)

def hls_path(url):
    HLS_CACHE.mkdir(exist_ok=True); return HLS_CACHE / (uuid.uuid5(uuid.NAMESPACE_URL, url).hex + Path(urllib.parse.urlsplit(url).path).suffix)

def hls_trim():
    """Понад межу — найстаріші шматки геть, крім тих, що потрібні просто зараз. Файл, який інший потік саме перейменував чи прибрав
    (недокачаний .part, що став шматком), пропускаємо: кеш качають кілька потоків одночасно."""
    def stat(x):
        try: return x.stat()
        except FileNotFoundError: return None
    seen = [(x, st) for x in HLS_CACHE.glob("*.*") if (st := stat(x))]
    total = sum(st.st_size for _, st in seen)
    for x, st in sorted(((x, st) for x, st in seen if x.suffix in (".ts", ".mp4") and time.time() - st.st_mtime > 900), key=lambda p: p[1].st_mtime):
        if total <= HLS_KEEP: break
        total -= st.st_size; x.unlink(missing_ok=True)

def hls_file(url, stream=None):
    """Шматок запису в кеші на диску: качаємо один раз, хоч би скільки його просили (прев'ю, аналіз, рендер, два вікна).
    stream — віддавати байти ще й плеєру, щойно приходять; такий запит не повторюємо — плеєр перепитає сам."""
    f = hls_path(url)
    with HLS_LOCKS(f.name):
        if f.is_file(): os.utime(f); return f                      # щойно потрібний — не викидати
        tmp = f.with_name(f"{uuid.uuid4().hex}.part")
        def attempt():
            with open_url(url) as r, open(tmp, "wb") as out:
                if stream: stream.start(int(r.headers.get("Content-Length") or 0))
                pump(r, [out.write] + ([stream.write] if stream else []), lambda got, total: HLS_GOT.__setitem__(f.name, (got, total)))   # для рядка «Буферизація»
        try: attempt() if stream else retrying(attempt, url); tmp.replace(f)
        finally: HLS_GOT.pop(f.name, None); tmp.unlink(missing_ok=True)
    hls_trim(); return f

class PlayerStream:
    """Відповідь плеєру потоком: заголовки — щойно відомий розмір, далі байти; плеєр перемотав далі — мовчки докачуємо в кеш."""
    def __init__(self, h, ctype): self.h, self.ctype, self.started, self.alive = h, ctype, False, True

    def start(self, total):
        self.h.send_response(200); self.h.send_header("Content-Type", self.ctype); self.h.send_header("Cache-Control", "no-store")
        if total: self.h.send_header("Content-Length", total)
        self.h.end_headers(); self.started = True

    def write(self, chunk):
        if not self.alive: return
        try: self.h.wfile.write(chunk)
        except OSError: self.alive = False

def hls_serve(h, url):
    """/hls для прев'ю: плейлист — з нашими адресами; шматок — потоком (плеєр не чекає на весь, інакше fragLoadTimeOut).
    Лише адреси відкритих записів: проксі не ходить куди завгодно."""
    if not any(url.startswith(v["base"]) for v in list(VODS.values())): raise PermissionError("Не адреса відкритого запису Twitch")
    if url.split("?")[0].endswith(".m3u8"): return h.reply(m3u8(url, lambda u: "/hls?u=" + urllib.parse.quote(u, safe="")).encode(), "application/vnd.apple.mpegurl")
    stream = PlayerStream(h, "video/mp2t" if hls_path(url).suffix == ".ts" else "video/mp4")
    try: f = hls_file(url, stream)
    except Exception as e:
        if not stream.started: raise
        print(datetime.now(), "hls", ascii(e)); h.close_connection = True; return   # заголовки вже пішли — плеєр побачить обрив і перепитає
    if stream.started: return
    try: h.reply(f.read_bytes(), stream.ctype)                     # уже був у кеші
    except ConnectionError: pass                                   # плеєр уже перемотав далі й закрив з'єднання

def hls_index(src, kind, upto=0):
    """Розбір плейлиста якості — один раз на запис (для трансляції, що триває, — знову, коли треба далі, ніж відомо)."""
    v = vod(src); idx = v.setdefault("idx", {})
    if kind not in idx or (upto and idx[kind][1] and sum(idx[kind][1][-1][:2]) < upto): idx[kind] = hls_parts(v[kind])
    return idx[kind]

def local_input(src, kind, a0, a1, say=lambda frac: None):
    """ffmpeg-вхід для [a0, a1]. Файл — як є. Запис Twitch: потрібні шматки качаються паралельно (8 з'єднань) у спільний кеш,
    а ffmpeg читає їх з диска — замість того, щоб тягнути по одному з мережі."""
    if not is_url(src): return ["-ss", f"{a0:.3f}", "-t", f"{a1 - a0:.3f}", "-i", src]
    init, parts = hls_index(src, kind, a1)
    need = [p for p in parts if p[0] + p[1] > a0 and p[0] < a1] or parts[-1:]
    urls = ([init] if init else []) + [u for _, _, u in need]
    files = dict(zip(urls, parallel([lambda p, u=u: (hls_file(u), p(1))[0] for u in urls], say, 8)))
    pl = HLS_CACHE / f"{uuid.uuid4().hex}.m3u8"                     # свій плейлист з локальних шматків
    pl.write_text("\n".join(["#EXTM3U", "#EXT-X-VERSION:6", f"#EXT-X-TARGETDURATION:{int(np.ceil(max(d for _, d, _ in need)))}", "#EXT-X-PLAYLIST-TYPE:VOD",
                             *([f'#EXT-X-MAP:URI="{files[init].name}"'] if init else []),
                             *(x for _, d, u in need for x in (f"#EXTINF:{d:.3f},", files[u].name)), "#EXT-X-ENDLIST"]), "utf-8")
    return ["-ss", f"{max(0.0, a0 - need[0][0]):.3f}", "-t", f"{a1 - a0:.3f}", "-i", str(pl)]

def hls_js():
    js = LIBS / "hls.min.js"
    if not js.is_file(): LIBS.mkdir(exist_ok=True); fetch(HLS_JS, js)
    return js.read_bytes()

def status():
    """Чи можна увійти, хто увійшов і код підтвердження, якщо вхід триває."""
    return dict(login=bool(TWITCH_CLIENT_ID), user=(rd(TW_FILE, None) or {}).get("user"), pending={k: TW_PENDING.get(k, "") for k in ("code", "uri", "err")})

def preview_progress():
    """Скільки байтів шматків, що качаються зараз, уже прийшло — для рядка «Буферизація»."""
    got = list(HLS_GOT.values()); return dict(got=sum(g for g, _ in got), total=sum(t for _, t in got))

def check_vod(url):
    """Перевірити посилання на запис і підготувати yt-dlp."""
    v = vod(url, fresh=True); return dict(title=v["title"], dur=v["dur"], thumb=v["thumb"])
