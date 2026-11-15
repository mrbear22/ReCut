#!/usr/bin/env python3
"""ShortsMaker — горизонтальне відео / стрім -> вертикальні шорти.
GUI відкривається вікном Edge (або в браузері). Дані: ../data (портативно) або ./data.
"""
import base64, importlib, io, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request, uuid, webbrowser, zipfile
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import brands, localai, publish

HERE = Path(__file__).resolve().parent
PACKAGED = (HERE.parent / "runtime").is_dir()                    # зібрана програма (інсталятор); інакше — запуск із сорсів
ROOT = HERE.parent if PACKAGED else HERE
DATA = ROOT / "data"; THUMBS, TRANS, PROJ, MODELS, MIXES = DATA / "thumbs", DATA / "transcripts", DATA / "projects", DATA / "models", DATA / "mixes"
TMP, RENDERS, CUDA, LIBS, FFDIR = DATA / "tmp", ROOT / "renders", DATA / "cuda", DATA / "libs", ROOT / "ffmpeg"
sys.path.insert(0, str(LIBS))                                      # бібліотеки, завантажені, коли вперше знадобились
for d in (THUMBS, TRANS, MODELS, MIXES, TMP, RENDERS): d.mkdir(parents=True, exist_ok=True)
# портативно: тимчасові файли й кеш моделей — лише в теці програми, ніде більше в системі
SYS_ENV = dict(os.environ)                                         # для вікна Edge: його тимчасові файли не мають жити в нашій теці (їх тримає BITS і програму не видалити)
tempfile.tempdir = str(TMP); os.environ.update(TMP=str(TMP), TEMP=str(TMP), HF_HOME=str(DATA / "hf"), HF_HUB_DISABLE_TELEMETRY="1")

def cuda_dirs():
    """Теки з DLL пакетів nvidia-*: встановлені в Python або завантажені програмою в data/cuda."""
    return [b for p in [*sys.path, str(CUDA)] for b in Path(p or ".", "nvidia").glob("*/bin")]

def use_cuda_dlls():
    for b in cuda_dirs():
        if str(b) not in os.environ["PATH"]:
            os.environ["PATH"] = str(b) + os.pathsep + os.environ["PATH"]
            if os.name == "nt": os.add_dll_directory(str(b))
use_cuda_dlls()
if sys.stdout is None or sys.executable.lower().endswith("pythonw.exe"):
    sys.stdout = sys.stderr = open(DATA / "log.txt", "a", encoding="utf-8", buffering=1)
SP = {"creationflags": 0x08000000} if os.name == "nt" else {}          # без вікон консолі для ffmpeg

CFG_FILE, HIST_FILE = DATA / "settings.json", DATA / "history.json"
CFG = dict(n_clips=8, min_len=20, max_len=50, encoder="auto", quality=21, stt=False, project="", defaults=[], port=8765,
           speed=dict(scan=5.0, stt=10.0))          # секунд відео за секунду роботи; уточнюється після кожного запуску
LEGACY = ("video", "preview", "logo", "font", "style", "title", "channel", "category", "badge", "layout", "region", "ai_key", "lang")
W, H = 1080, 1920
HOOK_LEN, HOOK_W, FPS_A, B = 3, 2.0, 5, 0.5
REGION, CHUNK, WIN = 1800, 300, 600    # область аналізу за замовчуванням; шматок транскрипції в кеші; вікно транскрипту на запит LLM, с
STT_MODEL, OLLAMA = "large-v3-turbo", "http://127.0.0.1:11434/api/"
ART = ("card", "stream", "text", "image", "chat", "alert", "shape", "emoji", "social")   # елементи, що малюються картинкою поверх відео
PAD = 40                                       # поле під тінь навколо плашки
ENC = {"nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "{q}", "-b:v", "0", "-pix_fmt", "yuv420p"],
       "amf":   ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "{q}", "-qp_p", "{q}", "-pix_fmt", "yuv420p"],
       "qsv":   ["-c:v", "h264_qsv", "-preset", "slow", "-global_quality", "{q}", "-pix_fmt", "nv12"],
       "cpu":   ["-c:v", "libx264", "-preset", "medium", "-crf", "{q}", "-pix_fmt", "yuv420p"]}
HW, JOB = [], dict(running=False, i=0, n=0, pct=0.0, err="", out="", id="", project="")
PAGES, STARTED = {}, time.time()                                 # відкриті вікна: id → коли востаннє озивалось
TASKS, CUR = {}, threading.local()                             # поступ кожної довгої операції окремо: ключ задає інтерфейс у запиті
LOCK, STT_LOCK, PICKED = threading.Lock(), threading.Lock(), set()
z = lambda x: (x - np.median(x)) / (x.std() + 1e-6)
ev = lambda v: max(2, int(round(v / 2)) * 2)
rd = lambda p, default: json.loads(p.read_text("utf-8")) if p.is_file() else default
save_cfg = lambda: CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=2), "utf-8")
on = lambda e: e.get("on", True)

def report_as(task, stage, text, frac=None, t0=None):
    """Етап, частка й скільки лишилось за швидкістю, з якою етап іде зараз. Порожній етап — операцію почато заново."""
    if not stage: TASKS.pop(task, None); return
    el = time.time() - t0 if t0 else 0
    TASKS[task] = dict(stage=stage, text=text, frac=frac, eta=el * (1 - frac) / frac if frac and frac > .03 and t0 else None)

def report(stage, text, frac=None, t0=None): report_as(getattr(CUR, "task", None) or "other", stage, text, frac, t0)

def learn(kind, media_s, t0):
    if media_s > 5: CFG["speed"][kind] = round(media_s / max(.1, time.time() - t0), 2); save_cfg()

def run(args, **kw): return subprocess.run(args, capture_output=True, **SP, **kw)
def ff(*a): return subprocess.Popen([ffbin("ffmpeg"), "-v", "error", *HW, *a, "-"], stdout=subprocess.PIPE, **SP).stdout

def probe(src):
    """(ширина, висота, тривалість, чи є звук)"""
    j = json.loads(subprocess.check_output([ffbin("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                            "-of", "json", src], **SP))
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"], float(j["format"]["duration"]), sum(s["codec_type"] == "audio" for s in j["streams"])

def all_audio(n):
    """Аргументи ffmpeg, що зводять усі n звукових доріжок (OBS пише гру й мікрофон окремо) в одну."""
    return [] if n < 2 else ["-filter_complex", "".join(f"[0:a:{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0[a]", "-map", "[a]"]

PREPARING, FAILED = set(), set()
def prepared(out, args):
    """Файл для прев'ю: шлях, коли готовий; '' — поки ffmpeg готує його у фоні; None — не вийшло."""
    if out.is_file(): return str(out)
    if out in FAILED: return None
    def make():
        tmp = out.with_name(out.stem + ".tmp" + out.suffix)
        if run([ffbin("ffmpeg"), "-y", "-v", "error", *args, str(tmp)]).returncode: FAILED.add(out); tmp.unlink(missing_ok=True)
        else: tmp.replace(out)
        PREPARING.discard(out)
    if out not in PREPARING: PREPARING.add(out); threading.Thread(target=make, daemon=True).start()
    return ""

preview_key = lambda src: uuid.uuid5(uuid.NAMESPACE_URL, f"{src}|{os.path.getmtime(src)}").hex[:16]

def preview_mix(src, n):
    """Зведений звук для прев'ю (браузер грає лише першу доріжку)."""
    return (prepared(MIXES / f"{preview_key(src)}.m4a", ["-i", src, "-vn", *all_audio(n), "-c:a", "aac", "-b:a", "160k"]) or "") if n > 1 else ""

def container(src):
    return subprocess.check_output([ffbin("ffprobe"), "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0", src], **SP, text=True).strip()

PROXIES_KEPT = 3                                                    # копії займають місце як оригінал — тримаємо лише останні
def preview_video(src):
    """Браузер не грає MPEG-TS, FLV, AVI навіть з H.264 усередині (так часто зберігаються записи Twitch):
    для прев'ю — копія в MP4 без перекодування; рендер бере оригінал."""
    if any(f in container(src) for f in ("mp4", "webm")): return src
    out = MIXES / f"{preview_key(src)}.mp4"
    if not out.is_file():
        for old in sorted((f for f in MIXES.glob("*.mp4") if ".tmp" not in f.name), key=os.path.getmtime)[:-(PROXIES_KEPT - 1) or None]: old.unlink(missing_ok=True)
    p = prepared(out, ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-c", "copy"])
    return src if p is None else p

_enc = {}
def pick_encoder():
    key = (CFG["encoder"], CFG["quality"])
    if key not in _enc:
        for k in ([CFG["encoder"]] if CFG["encoder"] != "auto" else ENC):
            if k == "cpu" or run([ffbin("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                                  *ENC[k][:2], "-f", "null", "-"]).returncode == 0:
                _enc[key] = k, [x.format(q=CFG["quality"]) for x in ENC[k]]; break
    return _enc[key]

# ── проєкти: кожен — окремий файл; новий бере копію елементів останнього ──
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
             elements=json.loads(json.dumps(CFG["defaults"])), cues=[], renders=[])
    with LOCK: return write_project({**p, **kw})

def projects():
    return sorted((json.loads(f.read_text("utf-8")) for f in PROJ.glob("*.json")), key=lambda p: -p["updated"])

def legacy_elements(q):
    """Плашка й розкладка старих версій -> елементи."""
    L = q.get("layout") or {}
    if "main" not in L: return []
    base = lambda: {"id": uuid.uuid4().hex[:8], "on": True, "anim": "none", "from": 0, "to": 0}
    els = [dict(base(), type="video", **{k: L["main"][k] for k in ("src", "x", "y", "w")})]
    if L.get("cam", {}).get("on"): els.append(dict(base(), type="cam", **{k: L["cam"][k] for k in ("src", "x", "y", "w")}))
    els.append(dict(base(), type="stream" if q.get("style") == "stream" else "card", x=L["card"]["x"], y=L["card"]["y"],
                    s=L["card"].get("s", 1), **{k: q.get(k, "") for k in ("preview", "logo", "title", "channel", "category", "badge", "font")}))
    return els

def migrate():
    """Історія рендерів і поточний стан старих версій -> окремі проєкти (один раз)."""
    if PROJ.is_dir(): return
    PROJ.mkdir()
    legacy = lambda q: dict(video=q.get("video", ""), region=q.get("region"), clips=q.get("clips", []), elements=legacy_elements(q))
    last = None
    for r in reversed(rd(HIST_FILE, [])):
        q = r.get("project", {})
        last = new_project(name=r.get("title", ""), created=r["date"], **legacy(q),
                           renders=[dict(id=r["id"], date=r["date"], out=r["out"], files=r["files"])])
        if legacy(q) == legacy(CFG): CFG["project"] = last["id"]
    if CFG.get("video") and not CFG["project"]: last = new_project(name=CFG.get("title", ""), **legacy(CFG)); CFG["project"] = last["id"]
    if last: CFG["defaults"] = load_project(CFG["project"] or last["id"])["elements"]
    for k in LEGACY: CFG.pop(k, None)
    save_cfg()

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

# ── аналіз моментів ──
def analyze_video(inp, sw, sh, length, t0):
    aw = 160; ah = ev(aw * sh / sw)
    pipe = ff(*inp, "-vf", f"fps={FPS_A},scale={aw}:{ah},format=gray", "-f", "rawvideo")
    prev, mot = None, []
    while len(buf := pipe.read(aw * ah)) == aw * ah:
        f = np.frombuffer(buf, np.uint8).reshape(ah, aw).astype(np.int16)
        mot.append(np.abs(f - (f if prev is None else prev)).mean()); prev = f
        if len(mot) % 25 == 0: report("scan", "Аналіз руху й звуку", min(.99, 0.9 * len(mot) / FPS_A / length), t0)   # звук — решта ~10 %
    mot = np.array(mot) if mot else np.zeros(1)
    return mot, np.where(mot > max(20, 5 * np.median(mot)))[0] / FPS_A

def analyze_audio(inp, nb, na):
    sr = 8000; k = int(sr * B)
    a = np.frombuffer(ff(*inp, "-vn", *all_audio(na), "-ac", "1", "-ar", str(sr), "-f", "s16le").read(), np.int16).astype(np.float32)
    if a.size < k: return np.zeros(nb)
    db = 10 * np.log10((a[:a.size // k * k].reshape(-1, k) ** 2).mean(1) + 1)
    return np.pad(db, (0, max(0, nb - len(db))), mode="edge")[:nb]

_FEAT = {}
def features(src, region):
    """Ознаки області [a0, a1] (None — перші REGION с); час усередині — від a0."""
    sw, sh, dur, audio = probe(src)
    a0, a1 = region or (0, REGION); a1 = min(float(a1), dur); a0 = max(0.0, min(float(a0), a1 - 1))
    key = (src, os.path.getmtime(src), a0, a1)
    if key not in _FEAT:
        nb = max(1, int((a1 - a0) / B)); inp = ("-ss", f"{a0:.3f}", "-t", f"{a1 - a0:.3f}", "-i", src); t0 = time.time()
        mot, cuts = analyze_video(inp, sw, sh, a1 - a0, t0); db = analyze_audio(inp, nb, audio); learn("scan", a1 - a0, t0)
        bi = np.minimum((np.arange(len(mot)) / FPS_A / B).astype(int), nb - 1)
        mot_b = np.bincount(bi, mot, nb) / np.maximum(np.bincount(bi, minlength=nb), 1)
        base = np.convolve(np.r_[np.full(8, db[0]), db], np.ones(8) / 8, "valid")[:nb]   # середнє за попередні 4 с
        ex = np.convolve(0.4 * z(db) + 0.4 * z(np.maximum(db - base, 0)) + 0.2 * z(mot_b), np.ones(2) / 2, "same")
        _FEAT.clear(); _FEAT[key] = dict(dur=dur, region=(a0, a1), audio=audio, db=db, ex=ex, cuts=cuts, sw=sw, sh=sh)
    return _FEAT[key]

def suggest(f):
    ex, db = f["ex"], f["db"]
    nb, h, lo, hi = len(ex), int(HOOK_LEN / B), int(CFG["min_len"] / B), int(CFG["max_len"] / B)
    cs, used, picked, idx = np.r_[0, np.cumsum(ex)], np.zeros(nb, bool), [], np.arange(nb)
    for _ in range(int(CFG["n_clips"])):                     # жадібно: найсильніший хук + напруга, кінець на тиші
        nxt = np.minimum.accumulate(np.where(used, idx, nb)[::-1])[::-1]
        best = None
        for s in range(nb - lo):
            b = min(s + hi, nxt[s])
            if b - s < lo: continue
            a = max(s + lo - 1, min(s + (lo + hi) // 2, b - 1)); e = a + int(np.argmin(db[a:b])) + 1
            sc = HOOK_W * (cs[min(s + h, nb)] - cs[s]) / h + (cs[e] - cs[s]) / (e - s)
            if best is None or sc > best[0]: best = (sc, s, e)
        if best is None or best[0] < 0: break
        used[best[1]:best[2]] = True; picked.append(best)
    out, t0 = [], f["region"][0]
    for sc, s, e in sorted(picked, key=lambda c: c[1]):
        a = max(0, (s + int(np.argmax(ex[s:s + h]))) * B - 0.5)          # пік хука на ~0.5 с
        prior = f["cuts"][(f["cuts"] <= a) & (f["cuts"] >= a - 1.5)]
        out.append(dict(a=t0 + float(prior[-1] if len(prior) else a), b=t0 + e * B, score=round(float(sc), 2)))
    return out

def with_context(clips, segs):
    """Кліп починається з початку фрази, в якій стався хук, і закінчується, коли фразу договорено."""
    for c in clips:
        c["a"] = min([c["a"]] + [a for _, a, b in segs if a <= c["a"] < b])
        c["b"] = max([c["b"]] + [b for _, a, b in segs if a < c["b"] <= b])
    return clips

# ── локальне розпізнавання мови (faster-whisper, як в AutoSubs) ──
# Програма легка: модель (1.6 ГБ) і, лише для відеокарт NVIDIA, CUDA-бібліотеки (1.9 ГБ) завантажуються один раз у data/
CUDA_PKGS, MODEL_BYTES = (("nvidia-cublas-cu12", ""), ("nvidia-cudnn-cu12", "9."), ("nvidia-cuda-nvrtc-cu12", "")), 1.62e9

# ── важке завантажується, коли вперше знадобиться: ffmpeg одразу після першого запуску, решта — під свою дію ──
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"   # з libass для субтитрів
STT_LIBS = ("faster-whisper==1.2.1 ctranslate2==4.9.0 onnxruntime==1.32.0 av==19.0.2 tokenizers==0.23.3 huggingface-hub==2.4.0 hf-xet==1.8.0 "
            "anyio==4.16.0 click==8.5.1 colorama==0.4.6 filelock==4.2.10 flatbuffers==25.12.19 fsspec==2026.9.0 h11==0.16.0 httpcore2==2.16.0 "
            "httpx2==2.16.0 idna==3.20 packaging==26.3 protobuf==7.36.2 pyyaml==6.0.3 tqdm==4.70.1 truststore==0.10.5 typing-extensions==4.16.0").split()
CV_LIBS = ["opencv-python-headless==4.14.0.94"]
LIB_LOCK = threading.Lock()                                        # паралельні аналіз і субтитри не качають те саме двічі

def download(url, dst, text, stage):
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ShortsMaker"}), timeout=60) as r, open(dst, "wb") as out:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            out.write(chunk); done += len(chunk); report(stage, text, done / total if total else None, t0)

def ffbin(name):
    """Шлях до ffmpeg/ffprobe. У зібраній програмі перший виклик завантажує ffmpeg у теку програми."""
    if not PACKAGED: return name                                   # із сорсів — той, що в PATH
    exe = FFDIR / f"{name}.exe"
    with LIB_LOCK:
        if not exe.is_file():
            z = TMP / "ffmpeg.zip"; download(FFMPEG_URL, z, "Завантажую ffmpeg, 90 МБ", "ffmpeg")
            part = FFDIR.with_name("ffmpeg.part"); shutil.rmtree(part, ignore_errors=True); part.mkdir()
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():
                    if "/bin/" in n and n.lower().endswith((".exe", ".dll")) and not n.lower().endswith("ffplay.exe"): (part / Path(n).name).write_bytes(zf.read(n))
            shutil.rmtree(FFDIR, ignore_errors=True); part.rename(FFDIR); z.unlink(missing_ok=True)   # тека з'являється лише цілою
    return str(exe)

def need_libs(specs, module, text, stage="libs"):
    """Колеса з PyPI (точні версії) -> data/libs, якщо модуля ще немає."""
    with LIB_LOCK:
        if importlib.util.find_spec(module): return
        files = []
        for spec in specs:
            name, ver = spec.split("==")
            urls = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{ver}/json", timeout=30))["urls"]
            files.append(next(f for f in urls if f["filename"].endswith("none-any.whl") or
                              (f["filename"].endswith("win_amd64.whl") and re.search(r"-(cp312|cp3\d+-abi3|py3)-", f["filename"]))))
        LIBS.mkdir(exist_ok=True); total, done, t0 = sum(f["size"] for f in files), 0, time.time()
        for f in files:
            whl = TMP / f["filename"]
            with urllib.request.urlopen(f["url"], timeout=60) as r, open(whl, "wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk); done += len(chunk); report(stage, text, done / total, t0)
            with zipfile.ZipFile(whl) as z: z.extractall(LIBS)
            whl.unlink()
        importlib.invalidate_caches()

def fetch_cuda():
    """Колеса nvidia-* з PyPI -> data/cuda, з прогресом у інтерфейсі."""
    from packaging.version import Version
    tag = "win_amd64" if os.name == "nt" else "manylinux"
    files = []
    for name, ver in CUDA_PKGS:
        rel = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30))["releases"]
        best = max((v for v, fs in rel.items() if v.startswith(ver) and not Version(v).is_prerelease and any(tag in f["filename"] for f in fs)), key=Version)
        files.append(next(f for f in rel[best] if tag in f["filename"] and f["filename"].endswith(".whl")))
    total, done, t0 = sum(f["size"] for f in files), 0, time.time()
    for f in files:
        whl = TMP / f["filename"]
        with urllib.request.urlopen(f["url"], timeout=60) as r, open(whl, "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk); done += len(chunk)
                report("stt", f"Завантажую бібліотеки NVIDIA, {total / 1e9:.1f} ГБ", done / total, t0)
        with zipfile.ZipFile(whl) as z: z.extractall(CUDA, [n for n in z.namelist() if n.startswith("nvidia/")])
        whl.unlink()
    use_cuda_dlls()

# ── розпізнавання мови — в окремому процесі: збій відеокарти (скидання драйвера) вбиває лише його, а не всю програму ──
class SttWorker:
    def __init__(self): self.proc, self.device, self.gpu_failures = None, None, 0

    def alive(self): return self.proc is not None and self.proc.poll() is None

    def start(self, device):
        exe = Path(sys.executable); py = exe.with_name("python.exe") if exe.with_name("python.exe").is_file() else exe   # pythonw не дає stdout
        self.proc = subprocess.Popen([str(py), str(Path(__file__)), "--stt-worker", device], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(DATA / "stt.log", "a", encoding="utf-8"), **SP)
        self.device = device; msg = self.read()
        if "error" in msg: self.stop(); raise RuntimeError(msg["error"])

    def stop(self):
        if self.alive(): self.proc.kill()
        self.proc = None

    def read(self):
        line = self.proc.stdout.readline()
        if not line: self.proc.wait(); raise ChildProcessError(f"процес розпізнавання впав (код {self.proc.returncode})")
        return json.loads(line)

    def transcribe(self, pcm, lang, tick):
        job = TMP / f"stt_{uuid.uuid4().hex}.pcm"; job.write_bytes(pcm)
        try:
            self.proc.stdin.write((json.dumps({"pcm": str(job), "lang": lang}) + "\n").encode()); self.proc.stdin.flush()
            while True:
                msg = self.read()
                if "tick" in msg: tick(msg["tick"])
                elif "error" in msg: raise RuntimeError(msg["error"])
                else: return msg["result"]
        finally: job.unlink(missing_ok=True)

STT = SttWorker()

def stt_model():
    """Бібліотеки, CUDA й модель — один раз; далі процес розпізнавання, що вже завантажив модель."""
    if STT.alive(): return STT
    need_libs(STT_LIBS, "faster_whisper", "Завантажую бібліотеки розпізнавання мови, 200 МБ", "stt")
    import ctranslate2
    gpu = ctranslate2.get_cuda_device_count() > 0 and STT.gpu_failures < 2   # двічі впала відеокарта — до перезапуску програми лише процесор
    if gpu and not any(b.parent.name == "cublas" for b in cuda_dirs()):
        try: fetch_cuda()
        except OSError as e: print("CUDA не завантажено, розпізнаю на процесорі:", e); gpu = False   # без інтернету — повільніше, але працює
    loading = not any(MODELS.rglob("model.bin")); t0, task = time.time(), getattr(CUR, "task", None)
    def watch():                                               # прогрес першого завантаження моделі — за розміром теки
        CUR.task = task
        while loading and not STT.alive():
            got = sum(f.stat().st_size for f in MODELS.rglob("*") if f.is_file())
            report("stt", "Завантажую модель мовлення, 1.6 ГБ", min(.99, got / MODEL_BYTES), t0); time.sleep(1)
    if loading: threading.Thread(target=watch, daemon=True).start()
    for dev in ["cuda"] * max(0, 2 - STT.gpu_failures) * gpu + ["cpu"]:   # відеокарта — дві спроби: скидання драйвера буває разовим
        try: STT.start(dev); return STT
        except (RuntimeError, ChildProcessError) as e:
            print(datetime.now(), "stt:", dev, "недоступно:", ascii(e)); STT.gpu_failures += dev == "cuda"
    raise RuntimeError("Розпізнавання мови не запускається")

def stt_run(pcm, lang, tick):
    """Шматок аудіо → речення зі словами. Процес на відеокарті впав — ще раз (скидання драйвера буває разове), потім на процесорі."""
    for _ in range(3):
        w = stt_model()
        try: return w.transcribe(pcm, lang, tick)
        except ChildProcessError as e:
            print(datetime.now(), "stt:", w.device, ascii(e)); STT.stop()
            if w.device != "cuda": raise RuntimeError("Розпізнавання мови аварійно зупинилось") from e
            STT.gpu_failures += 1
            report("stt", "Збій відеокарти — продовжую" + (" на процесорі" if STT.gpu_failures >= 2 else ""), None)
    raise RuntimeError("Розпізнавання мови аварійно зупинилось")

def stt_worker(device):
    """Окремий процес: модель у пам'яті, завдання — рядки JSON у stdin, відповіді — у stdout."""
    out, sys.stdout = sys.stdout, sys.stderr                  # сторонні print-и бібліотек не ламають протокол
    send = lambda m: (out.write(json.dumps(m) + "\n"), out.flush())
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel(STT_MODEL, device=device, compute_type="float16" if device == "cuda" else "int8", download_root=str(MODELS))
        list(m.transcribe(np.zeros(16000, np.float32), vad_filter=False)[0])   # пробний прохід: несправна CUDA впаде тут, а не на відео
    except Exception as e: return send({"error": str(e)[:300]})
    send({"ready": device})
    for line in sys.stdin:
        try:
            job = json.loads(line); audio = np.fromfile(job["pcm"], np.int16).astype(np.float32) / 32768
            segs, _ = m.transcribe(audio, language=job["lang"] or None, word_timestamps=True, vad_filter=True, condition_on_previous_text=False)   # VAD: без вигадок на музиці
            res = []
            for sg in segs: res.append([sg.text.strip(), sg.start, sg.end, [[w.word.strip(), w.start, w.end] for w in sg.words]]); send({"tick": sg.end})
            send({"result": res})
        except Exception as e: send({"error": str(e)[:300]})

def whisper(src, t0, lang, tick, na, track=None):
    """Шматок [t0, t0 + CHUNK) -> слова й речення з абсолютним часом: [текст, початок, кінець]; tick(с розпізнано).
    track — одна звукова доріжка (окремий спікер), None — усі зведені."""
    audio = ["-map", f"0:a:{track}"] if track is not None else all_audio(na)
    r = run([ffbin("ffmpeg"), "-v", "error", "-ss", str(t0), "-t", str(CHUNK), "-i", src, "-vn", *audio, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    if r.returncode: raise RuntimeError("Аудіо для розпізнавання: " + r.stderr.decode("utf-8", "replace")[-300:])
    words, sg = [], []
    for text, a, b, ws in stt_run(r.stdout, lang, tick):
        sg.append([text, t0 + a, t0 + b]); words += [[w, t0 + wa, t0 + wb] for w, wa, wb in ws]
    return dict(words=words, segs=sg, len=len(r.stdout) / 32000)

def transcript(src, a0, a1, lang, track=None, label="Розпізнаю мову"):
    """(слова, речення) в [a0, a1]: шматки по CHUNK с кешуються на диску. track — лише одна звукова доріжка."""
    na = probe(src)[3]                                         # зведені доріжки й кожна окремо — різний кеш
    tag = uuid.uuid5(uuid.NAMESPACE_URL, f"{src}|{os.path.getmtime(src)}|{STT_MODEL}|{lang}" + (f"|track{track}" if track is not None else f"|mix{na}" * (na > 1))).hex[:16]
    path = lambda k: TRANS / f"{tag}_{k}.json"
    ks = range(int(a0 // CHUNK), int(np.ceil(a1 / CHUNK))); todo = [k for k in ks if not path(k).is_file()]; words, segs = [], []
    with STT_LOCK:
        if todo: stt_model()
        t0, done = time.time(), 0.0
        for k in todo:
            tick = lambda s: report("stt", label, min(.99, (done + s) / (len(todo) * CHUNK)), t0)
            t = whisper(src, k * CHUNK, lang, tick, na, track); path(k).write_text(json.dumps(t, ensure_ascii=False), "utf-8"); done += t["len"]
        learn("stt", done, t0)
    for k in ks: t = json.loads(path(k).read_text("utf-8")); words += t["words"]; segs += t["segs"]
    inside = lambda x: x[2] > a0 and x[1] < a1
    return [w for w in words if inside(w)], [s for s in segs if inside(s)]

def phrases(words, n):
    """Слова -> фрази субтитрів: до n слів, розрив на паузі чи кінці речення."""
    out = []
    for w in words:
        if out and len(out[-1]) < n and w[1] - out[-1][-1][2] < 0.5 and not out[-1][-1][0].endswith((".", "!", "?", "…")): out[-1].append(w)
        else: out.append([w])
    return out

def make_cues(words, n):
    """Доріжка субтитрів: фраза = репліка з часом кожного слова (k) для підсвітки."""
    ph = phrases(words, n)
    return [dict(a=p[0][1], b=min(p[-1][2] + 0.3, nx[0][1] if nx else 1e9), text=" ".join(w[0] for w in p), k=[w[1] for w in p])
            for p, nx in zip(ph, ph[1:] + [None])]

# ── контекст моментів через локальну LLM (Ollama, безкоштовно; якщо не запущена — за фразами транскрипту) ──
PROMPT = """Ти вирізаєш вірусні вертикальні шорти з довгого відео чи стріму.
Рядки транскрипту — "[початок-кінець] текст", час у секундах. Раптові гучні моменти (сміх, крики, реакції) на: {peaks}.
Обери до {n} найсмішніших чи найзахопливіших завершених моментів. Кожен кліп триває {lo}-{hi} с, починається там, де починається
потрібний контекст (підводка), і закінчується одразу після панчлайну чи реакції.
Відповідай лише JSON: {{"clips": [{{"start": сек, "end": сек, "score": 1-10, "why": "коротко українською: що відбувається і чим цікаво"}}]}}

{lines}"""

def ollama_model():
    """Модель локального ШІ або None (портативна Ollama стартує сама, якщо вже завантажена)."""
    return AI.model()

def safe_ollama_model():
    try: return ollama_model()
    except Exception as e: print(datetime.now(), "local AI unavailable:", ascii(e)); return None

LLM_TIMEOUT, LLM_TRIES = 180, 2                                   # завислий ШІ не тримає аналіз; збій — ще одна спроба

def ask_llm(model, prompt):
    """Кандидати від ШІ для одного вікна; збій чи сміття у відповіді — порожньо (аналіз не падає)."""
    body = json.dumps(dict(model=model, stream=False, format="json", options=dict(temperature=0, seed=0, num_ctx=16384),
                           messages=[{"role": "user", "content": prompt}])).encode()
    for attempt in range(LLM_TRIES):
        try:
            with STT_LOCK, urllib.request.urlopen(urllib.request.Request(OLLAMA + "chat", body), timeout=LLM_TIMEOUT) as r:   # не разом з Whisper: ділять відеокарту
                raw = json.loads(json.load(r)["message"]["content"]).get("clips", [])
            return [dict(start=float(c["start"]), end=float(c["end"]), score=float(c.get("score", 0)), why=str(c.get("why", "")))
                    for c in raw if isinstance(c, dict) and "start" in c and "end" in c]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e: print(datetime.now(), "llm attempt", attempt + 1, "failed:", ascii(e))
    return []

def ai_moments(f, segs, model):
    """Моменти за змістом: LLM читає транскрипт вікнами по WIN с, найкращі без перетинів."""
    (a0, a1), ex = f["region"], f["ex"]; n, lo, hi = int(CFG["n_clips"]), CFG["min_len"], CFG["max_len"]
    peaks = []
    for i in np.argsort(ex)[::-1]:
        if all(abs(i - j) * B >= 10 for j in peaks): peaks.append(i)
        if len(peaks) >= 3 * n: break
    peaks = sorted(a0 + i * B for i in peaks); cand = []; wins = np.arange(a0, a1, WIN); t0 = time.time()
    for i, w0 in enumerate(wins):                            # вікно захоплює max_len до себе: контекст на межі не губиться
        lines = "\n".join(f"[{a:.1f}-{b:.1f}] {t}" for t, a, b in segs if w0 - hi <= a < w0 + WIN)
        if not lines: continue
        report("llm", "Шукаю моменти", i / len(wins), t0)
        cand += ask_llm(model, PROMPT.format(n=n, lo=lo, hi=hi, lines=lines,
                                             peaks=", ".join(f"{p:.0f}" for p in peaks if w0 - hi <= p < w0 + WIN) or "none"))
    out = []
    for c in sorted(cand, key=lambda c: -c["score"]):
        a = max(a0, c["start"]); b = min(max(c["end"], a + lo), a + hi, a1)
        if b - a >= 1 and not any(a < o["b"] and b > o["a"] for o in out): out.append(dict(a=a, b=b, why=str(c.get("why", ""))[:200]))
        if len(out) == n: break
    return sorted(out, key=lambda c: c["a"])

# ── пошук вебкамери ──
def detect_cam(src):
    """Обличчя (Haar) + статична зона навколо нього (кімната не змінюється, гра — так) + стійкі межі рамки."""
    need_libs(CV_LIBS, "cv2", "Завантажую OpenCV, 40 МБ")
    import cv2
    sw, sh, dur, _ = probe(src); aw = 640; ah = ev(aw * sh / sw); n = 32
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    frames, faces = [], []
    for i in range(n):
        raw = run([ffbin("ffmpeg"), "-v", "error", "-ss", f"{dur * (0.04 + 0.92 * i / (n - 1)):.2f}", "-i", src, "-frames:v", "1",
                   "-vf", f"scale={aw}:{ah}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
        if len(raw) < aw * ah: continue
        g = np.frombuffer(raw[:aw * ah], np.uint8).reshape(ah, aw); frames.append(g)
        faces += [(x + w / 2, y + h / 2, w) for x, y, w, h in casc.detectMultiScale(g, 1.1, 6, minSize=(18, 18))]
    if len(frames) < 4: raise RuntimeError("Не вдалося прочитати кадри")
    if len(faces) < max(3, len(frames) * 0.15): return None
    F = np.array(faces)
    near = [(np.hypot(*(F[:, :2] - f[:2]).T) < f[2] * 0.6).sum() for f in F]   # найчастіше місце обличчя
    c = F[np.hypot(*(F[:, :2] - F[int(np.argmax(near))][:2]).T) < F[int(np.argmax(near))][2] * 0.6]
    cx, cy, fw = np.median(c, axis=0)
    st = np.stack(frames).astype(np.float32)
    std = cv2.GaussianBlur(st.std(0), (0, 0), 1)                       # мінливість у часі: гра висока, кімната низька
    pe = [np.mean([np.abs(cv2.Sobel(g, cv2.CV_32F, *d)) > 40 for g in frames], 0) for d in ((1, 0), (0, 1))]  # стійкі межі
    ring = std[max(0, int(cy - 2 * fw)):int(cy + 2 * fw), max(0, int(cx - 2 * fw)):int(cx + 2 * fw)]
    inner = np.percentile(ring, 30); thr = min((inner + np.percentile(std, 80)) / 2, max(6, 3 * inner + 4))
    def edge(prof, lines, start, stop, step):
        """Від обличчя назовні: перша точка, де мінливість стабільно вище порогу (почалась гра)."""
        for v in range(int(start), int(stop), step):
            nxt = prof[v:v + 4 * step:step] if step > 0 else prof[max(0, v - 3):v + 1]
            if len(nxt) and (nxt > thr).all():
                lo_, hi_ = sorted((v - 6 * step, v + 2 * step))                # уточнюємо по лінії рамки, якщо є
                seg = lines[max(0, lo_):max(0, hi_) + 1]
                if len(seg) and seg.max() > 0.5: v = max(0, lo_) + int(np.argmax(seg)) + (1 if step > 0 else 0)
                return v
        return stop - step if step > 0 else 0
    ys, xs = slice(max(0, int(cy - fw)), int(cy + fw)), slice(max(0, int(cx - fw)), int(cx + fw))
    colp, rowp = std[ys].mean(0), std[:, xs].mean(1)
    coll, rowl = pe[0][ys].mean(0), pe[1][:, xs].mean(1)
    L = edge(colp, coll, cx - fw * 0.8, -1, -1); R = edge(colp, coll, cx + fw * 0.8, aw + 1, 1)
    T = edge(rowp, rowl, cy - fw * 0.8, -1, -1); Bt = edge(rowp, rowl, cy + fw * 0.8, ah + 1, 1)
    L, T, R, Bt = max(0, L), max(0, T), min(aw, R), min(ah, Bt)
    return [L / aw, T / ah, (R - L) / aw, (Bt - T) / ah]

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

def make_card(el):
    """Плашка відео (прев'ю + назва + канал) або стріму (аватар з LIVE): (RGBA з полем PAD під тінь, ширина, висота)."""
    s = float(el.get("s", 1.0)); font = pick_font(el.get("font"))[1]; k = lambda v: max(1, round(v * s)); g = lambda n: el.get(n) or ""
    cw, pad = k(968), k(28)
    if el["type"] == "stream":
        av, gap = k(128), k(26); tx = cw - 2 * pad - av - gap
        nf, nl, _ = fit_lines(g("channel"), font, k(42), tx, 1)
        tf, tl, ts = fit_lines(g("title"), font, k(32), tx, 2)
        cf, cl, _ = fit_lines(g("category"), font, k(28), tx, 1)
        blocks = [(nf, nl, (255, 255, 255), k(42) * 1.3), (tf, tl, (222, 222, 227), ts * 1.3), (cf, cl, (191, 148, 255), k(28) * 1.4)]
        text_h = int(sum(len(l) * lh for _, l, _, lh in blocks))
        ch = max(av + k(22), text_h) + 2 * pad
        img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); shadow(img, cw, ch, k(18))
        d = ImageDraw.Draw(img); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), k(18), fill=(24, 24, 27))
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
    else:
        th = k(200); tw = th * 16 // 9; tx = cw - 3 * pad - tw
        tf, lines, size = fit_lines(g("title"), font, k(44), tx, 3, k(20))
        cf = ImageFont.truetype(font, k(32)); lh = int(size * 1.3)
        text_h = lh * len(lines) + (int(k(32) * 1.6) if g("channel") else 0)
        ch = max(th, text_h) + 2 * pad
        img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); shadow(img, cw, ch, k(44))
        d = ImageDraw.Draw(img); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), k(44), fill="white")
        src = Image.open(g("preview")) if Path(g("preview") or "-").is_file() else Image.new("RGB", (16, 9), (205, 205, 210))
        t, m = round_img(src, (tw, th), k(18)); tx0 = PAD + pad; img.paste(t, (tx0, PAD + (ch - th) // 2), m)
        x, y = tx0 + tw + pad, PAD + (ch - text_h) // 2
        for l in lines: d.text((x, y), l, font=tf, fill=(15, 15, 15)); y += lh
        if g("channel"):
            y += int(k(32) * 0.3)
            if a := avatar(g("logo"), int(k(32) * 1.4)): img.paste(a[0], (x, y + (k(32) - a[0].width) // 2 + k(4)), a[1]); x += a[0].width + k(14)
            d.text((x, y), g("channel"), font=cf, fill=(96, 96, 96))
    return img, cw, ch

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
               stroke_width=stroke, stroke_fill="black")
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
    img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); shadow(img, cw, ch, k(16))
    d = ImageDraw.Draw(img); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), k(16), fill=(20, 20, 24, 235))
    for i, l in enumerate(lines):
        x, y = PAD + pad, PAD + pad + i * lh
        if i == 0 and name and l.startswith(name + ":"):
            d.text((x, y), name + ":", font=f, fill=el.get("nameColor", "#a970ff")); x += f.getlength(name + ": "); l = l[len(name) + 1:].lstrip()
        d.text((x, y), l, font=f, fill=(240, 240, 245))
    return img, cw, ch

def make_alert(el):
    """Алерт стріму (донат, фолов, підписка): акцентна смуга, заголовок, повідомлення."""
    s = float(el.get("s", 1)); k = lambda v: max(1, round(v * s)); font = pick_font(el.get("font"))[1]; acc = el.get("color", "#ffcc33")
    f1, f2, cw, pad = ImageFont.truetype(font, k(46)), ImageFont.truetype(font, k(32)), k(860), k(28)
    tl, ml = wrap(el.get("title") or "", f1, cw - 2 * pad), wrap(el.get("text") or "", f2, cw - 2 * pad)[:4] if el.get("text") else []
    lh1, lh2 = round(k(46) * 1.25), round(k(32) * 1.35)
    ch = k(10) + 2 * pad + lh1 * len(tl) + (k(12) + lh2 * len(ml) if ml else 0)
    img = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0)); shadow(img, cw, ch, k(22))
    d = ImageDraw.Draw(img); d.rounded_rectangle((PAD, PAD, PAD + cw, PAD + ch), k(22), fill=acc)
    d.rounded_rectangle((PAD, PAD + k(10), PAD + cw, PAD + ch), k(22), fill=(24, 24, 28))
    y = PAD + k(10) + pad
    for l in tl: d.text((PAD + cw / 2, y), l, font=f1, fill=acc, anchor="ma"); y += lh1
    y += k(12)
    for l in ml: d.text((PAD + cw / 2, y), l, font=f2, fill=(235, 235, 240), anchor="ma"); y += lh2
    return img, cw, ch

def make_shape(el):
    """Стрілка, обвідка колом чи рамкою — показати на щось у кадрі."""
    w, h, t, col = round(float(el.get("w", 320))), round(float(el.get("h", 320))), max(2, round(float(el.get("thick", 12)))), el.get("color", "#ff3b30")
    img = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    box = (PAD + t / 2, PAD + t / 2, PAD + w - t / 2, PAD + h - t / 2); kind = el.get("shape", "circle")
    if kind == "circle": d.ellipse(box, outline=col, width=t)
    elif kind == "rect": d.rounded_rectangle(box, radius=t * 1.5, outline=col, width=t)
    else:                                                        # стрілка вправо, далі повертається на кут
        cy, hd = PAD + h / 2, min(h, w * 0.45)
        d.line((PAD + t, cy, PAD + w - hd * 0.8, cy), fill=col, width=t)
        d.polygon([(PAD + w, cy), (PAD + w - hd, cy - hd / 2), (PAD + w - hd, cy + hd / 2)], fill=col)
        if el.get("rot"): img = img.rotate(-float(el["rot"]), expand=True, resample=Image.BICUBIC); w, h = img.width - 2 * PAD, img.height - 2 * PAD
    return img, w, h

def make_emoji(el):
    """Емодзі-реакція кольоровим шрифтом системи."""
    pick_font(None); path = next((FONTS[n] for n in ("Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji") if n in FONTS), pick_font(None)[1])
    f = ImageFont.truetype(path, max(16, round(float(el.get("size", 160))))); txt = el.get("text") or "😂"
    l, t, r, b = f.getbbox(txt); img = Image.new("RGBA", (r - l + 2 * PAD, b - t + 2 * PAD), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((PAD - l, PAD - t), txt, font=f, embedded_color=True); return img, r - l, b - t

def art(el): return {"card": make_card, "stream": make_card, "text": make_text, "image": make_image,
                     "chat": make_chat, "alert": make_alert, "shape": make_shape, "emoji": make_emoji, "social": make_social}[el["type"]](el)

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
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((PAD, PAD + 12, PAD + cw, PAD + ch + 12), r, fill=(0, 0, 0, 110))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))

# ── рендер ──
def kept(a, b, cuts):
    """Інтервали джерела, що лишаються в кліпі [a, b] після вирізання пропусків."""
    out, t = [], a
    for x, y in sorted(cuts) + [(b, b)]:
        if min(x, b) - t > 0.05: out.append((t, min(x, b)))
        t = max(t, y)
    return out

ass_col = lambda c: f"&H00{c[5:7]}{c[3:5]}{c[1:3]}&".upper()     # #rrggbb -> ASS &H00BBGGRR&

def cue_owner(c, subs_all):
    """Елемент «Субтитри», якому належить репліка (кожен спікер — свій елемент); без позначки — першому."""
    return next((e for e in subs_all if e["id"] == c.get("sid")), subs_all[0] if subs_all else None)

def subs_ass(cues, keep, subs_all):
    """ASS кліпу: кожен увімкнений елемент «Субтитри» — свій стиль і місце, зі своїми репліками; час — уже без вирізаних пропусків."""
    ts = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    styles, lines = [], []
    for n, el in enumerate(subs_all):
        if not on(el): continue
        size = float(el.get("size", 84)); x, y, w = float(el["x"]), float(el["y"]), float(el.get("w", 900))
        hl, base = ass_col(el.get("hl", "#ffcc33")), ass_col(el.get("color", "#ffffff"))
        intro = {"pop": r"\fscx80\fscy80\t(0,90,\fscx100\fscy100)", "fade": r"\fad(150,0)"}.get(el.get("anim", "pop"), "")
        styles.append(f"Style: S{n},{pick_font(el.get('font'))[0].replace(',', ' ')},{size:.0f},{base},{base},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,"
                      f"{float(el.get('outline', 6)):.1f},{size * 0.04:.1f},5,{max(0, x):.0f},{max(0, W - x - w):.0f},0,1")
        for c in (c for c in cues if cue_owner(c, subs_all) is el):
            text = re.sub(r"[{}\\]", "", c["text"].upper() if el.get("upper") else c["text"]); words = text.split()
            if not words: continue
            k = c.get("k") if len(c.get("k") or []) == len(words) else [c["a"] + i * (c["b"] - c["a"]) / len(words) for i in range(len(words))]
            spans = list(zip(k, k[1:] + [c["b"]], range(len(words)))) if el.get("karaoke", True) else [(c["a"], c["b"], -1)]
            first = True
            for s0_, e_, i in spans:
                body = " ".join(f"{{\\1c{hl}}}{t}{{\\1c{base}}}" if j == i else t for j, t in enumerate(words)); off = 0.0
                for s0, s1 in keep:                                    # репліка через вирізаний пропуск ділиться на шматки
                    a, b = max(s0_, s0) - s0 + off, min(e_, s1) - s0 + off; off += s1 - s0
                    if b - a < 0.02: continue
                    lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},S{n},,0,0,0,,{{\\an5\\pos({x + w / 2:.0f},{y + size * 0.7:.0f}){intro * first}}}{body}"); first = False
    return (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) + "\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + "\n".join(lines) + "\n")

def when(e):
    """Час показу елемента в кліпі: з/до, секунди від початку вже без пропусків."""
    segs = [(float(a or 0), float(b or 0)) for a, b in e.get("segs") or [(e.get("from"), e.get("to"))]]
    if segs == [(0, 0)]: return ""
    return ":enable='" + "+".join(f"between(t,{a},{b or 1e9})" for a, b in segs) + "'"

def clip_elements(elements, c):
    """Елементи для кліпу: свої частини показу (segs) замість спільних з/до; сховані в кліпі й ті, яких у кліп не додали, — геть."""
    own, out = c.get("segs") or {}, []
    for e in elements:
        segs = own.get(e["id"])
        if segs is None:
            if not e.get("solo"): out.append(e)
        elif segs: out.append(dict(e, segs=segs, **{"from": segs[0][0], "to": segs[-1][1]}))   # анімація — на першому вході й останньому виході
    return out

def overlay_art(e, i, size, last, nxt):
    """Елемент-картинка (вхід i) з анімацією входу."""
    st, en, anim = float(e.get("from") or 0), float(e.get("to") or 0), e.get("anim", "none")
    x, y, pre = f"{int(e['x']) - PAD}", f"{int(e['y']) - PAD}", []
    if anim != "none": pre += ["format=rgba", f"fade=t=in:st={st}:d=0.3:alpha=1"] + [f"fade=t=out:st={max(st, en - 0.3)}:d=0.3:alpha=1"] * (en > 0)
    if anim == "pop":
        k = f"(0.6+0.4*clip((t-{st})/0.25\\,0\\,1))"
        pre.append(f"scale=w='iw*{k}':h='ih*{k}':eval=frame"); x, y = f"'{x}+({size[0]}-w)/2'", f"'{y}+({size[1]}-h)/2'"
    if anim == "slide": y = f"'{y}+140*(1-clip((t-{st})/0.35,0,1))'"
    f = [f"[{i}:v]{','.join(pre)}[a{i}]"] if pre else []
    return f + [f"[{last}][{f'a{i}' if pre else f'{i}:v'}]overlay={x}:{y}:shortest=1{when(e)}[{nxt}]"]

def build_filter(sw, sh, elements, keep, na, inp, sizes, subs):
    """na: скільки звукових доріжок; inp: (id елемента, роль) -> номер входу ffmpeg; sizes: id -> розмір картинки елемента."""
    els = [e for e in elements if on(e) and e["type"] not in ("subs", "bg", "music")]; vids = [e for e in els if e["type"] in ("video", "cam")]
    bg = next((e for e in elements if e["type"] == "bg" and on(e)), {}); net = sum(e - s for s, e in keep)
    f, src, audio, asrc = [], "0:v", int(na > 0), "0:a"
    if na > 1: f.append("".join(f"[0:a:{i}]" for i in range(na)) + f"amix=inputs={na}:normalize=0[am]"); asrc = "am"   # звучать усі доріжки
    if len(keep) > 1:                                              # пропуски вирізано: склеюємо збережені шматки
        n, seg = len(keep), [(s - keep[0][0], e - keep[0][0]) for s, e in keep]
        for t, p, s0 in (("v", "", "0:v"), ("a", "a", asrc))[:1 + audio]:
            f.append(f"[{s0}]{p}split={n}" + "".join(f"[p{t}{i}]" for i in range(n)))
            f += [f"[p{t}{i}]{p}trim=start={s:.3f}:end={e:.3f},{p}setpts=PTS-STARTPTS[k{t}{i}]" for i, (s, e) in enumerate(seg)]
        f.append("".join(f"[kv{i}]" + (f"[ka{i}]" if audio else "") for i in range(n)) + f"concat=n={n}:v=1:a={int(audio)}[cv]" + "[ca]" * audio)
        src = "cv"
    f += [f"[{src}]split={1 + len(vids)}[bg0]" + "".join(f"[s{i}]" for i in range(len(vids))),
          f"[bg0]scale={W}:{H},drawbox=color={bg['color']}:t=fill[bg]" if bg.get("style") == "color" else
          f"[bg0]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"     # блюр у 1/4 роздільності
          f"gblur=sigma={float(bg.get('blur', 5)):g},eq=brightness={-float(bg.get('dim', 0.12)):g},scale={W}:{H}[bg]"]
    last = "bg"
    for n, e in enumerate(els, 1):
        if e["type"] in ART: f += overlay_art(e, inp[e["id"], "art"], sizes[e["id"]], last, f"l{n}")
        elif e["type"] == "progress":                              # смуга росте від 0 до повної ширини за кліп
            f += [f"color=c={e.get('color', '#ffcc33')}:s={W}x{ev(float(e.get('h', 12)))}:r=30[pg{n}]",
                  f"[{last}][pg{n}]overlay=x='-w+w*t/{net:.3f}':y={int(e['y'])}:shortest=1{when(e)}[l{n}]"]
        else:
            c, dw, dh = layer(e, sw, sh); i, x, y = vids.index(e), int(e["x"]), int(e["y"])
            if (e["id"], "mask") in inp: f += [f"[s{i}]{c},format=rgba[c{n}]", f"[c{n}][{inp[e['id'], 'mask']}:v]alphamerge[e{n}]"]
            else: f.append(f"[s{i}]{c}[e{n}]")
            f.append(f"[{last}][e{n}]overlay={x}:{y}:shortest=1{when(e)}[l{n}]")   # маска-картинка довша за склеєне відео — кліп не подовжується
            if (e["id"], "ring") in inp:
                b = round(float(e["bw"])); f.append(f"[l{n}][{inp[e['id'], 'ring']}:v]overlay={x - b}:{y - b}:shortest=1{when(e)}[r{n}]"); last = f"r{n}"; continue
        last = f"l{n}"
    f.append(f"[{last}]{'ass=subs.ass:fontsdir=.' if subs else 'null'}[v]")    # ffmpeg працює в теці з subs.ass і шрифтом
    return ";".join(f)

def out_pos(x, keep):
    """Час у готовому кліпі для моменту x джерела (вирізані пропуски не рахуються)."""
    return sum(min(x, e) - s for s, e in keep if x > s)

def music_parts(els, net):
    """Шматки музики кліпу: (файл, з якої секунди файлу, де в кліпі, скільки, гучність, наростання, згасання).
    Момент треку = зсув треку + час у кліпі, тож розрізані шматки грають у такт, ніби трек не переривався."""
    out = []
    for e in els:
        if e["type"] != "music" or not on(e) or not Path(e.get("path", "")).is_file(): continue
        off, dur, vol = float(e.get("off") or 0), float(e.get("dur") or 1e9), float(e.get("vol", 1))
        segs = [(float(a or 0), float(b or 0) or net) for a, b in e.get("segs") or [(e.get("from"), e.get("to"))]]
        for k, (a, b) in enumerate(segs):
            a, b = max(a, -off, 0), min(b, net, dur - off)
            if b - a < .05: continue
            fin = float(e.get("fin") or 0) if k == 0 else .02                       # усередині — лише проти клацання
            fout = max(float(e.get("fout") or 0) if k == len(segs) - 1 else 0, .03)
            out.append((e["path"], off + a, a, b - a, vol, min(fin, (b - a) / 2), min(fout, (b - a) / 2)))
    return out

PEAKS = {}
def peaks(path, rate=50):
    """Гучність треку для хвилі на таймлайні: rate значень на секунду, 0–255, base64."""
    if path not in PEAKS:
        raw, step = run([ffbin("ffmpeg"), "-v", "error", "-i", path, "-ac", "1", "-ar", str(rate * 40), "-f", "u8", "-"]).stdout, 40
        v = [max(abs(x - 128) for x in raw[i:i + step]) for i in range(0, len(raw), step)]
        top = max(v, default=0) or 1
        PEAKS[path] = dict(rate=rate, b64=base64.b64encode(bytes(min(255, x * 255 // top) for x in v)).decode())
    return PEAKS[path]

def audio_filter(main, parts, first_input, video_vol, net):
    """Звук кліпу: звук відео з потрібною гучністю + шматки музики з фейдами. Повертає (фільтри, мітка виходу)."""
    f, mix = [], []
    if main: f.append(f"[{main}]volume={video_vol:.3f}[av]"); mix.append("[av]")
    for k, (_, _, at, length, vol, fin, fout) in enumerate(parts):
        fx = [f"atrim=0:{length:.3f}", "asetpts=PTS-STARTPTS", f"volume={vol:.3f}"]
        if fin: fx.append(f"afade=t=in:st=0:d={fin:.3f}")
        if fout: fx.append(f"afade=t=out:st={length - fout:.3f}:d={fout:.3f}")
        fx.append(f"adelay={round(at * 1000)}:all=1")
        f.append(f"[{first_input + k}:a]" + ",".join(fx) + f"[mu{k}]"); mix.append(f"[mu{k}]")
    if not mix: return f, None
    f.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=longest,atrim=0:{net:.3f}[aout]")   # мікс не довший за кліп
    return f, "aout"

def render(pid, clips, elements, cues):
    try:
        pr = load_project(pid); src = pr["video"]; sw, sh, _, na = probe(src); _, args = pick_encoder()
        subs_all = [e for e in elements if e["type"] == "subs"]; subs = any(on(e) for e in subs_all)   # кожен спікер — свій елемент «Субтитри»
        name = re.sub(r'[<>:"/\\|?*]+', " ", pr["name"] or Path(src).stem).strip(" .") or "shorts"
        out = RENDERS / name; out.mkdir(parents=True, exist_ok=True); used = set()   # тека проєкту; той самий кліп — той самий файл
        rec = dict(id=JOB["id"], date=time.time(), out=str(out), files=[])
        save_rec = lambda: update_project(pid, lambda p: p.__setitem__("renders", [rec] + [r for r in p["renders"] if r["id"] != rec["id"]]))
        save_rec(); JOB["out"] = str(out)
        with tempfile.TemporaryDirectory() as tmp:
            pngs, sizes = [], {}                                   # (id, роль, файл): картинки елементів, маски й рамки відео
            def add(e, role, img): p = Path(tmp, f"{e['id']}_{role}.png"); img.save(p); pngs.append((e["id"], role, str(p))); return img.size
            for e in (e for e in elements if on(e)):
                if e["type"] in ART: sizes[e["id"]] = add(e, "art", art(e)[0])
                if e["type"] in ("video", "cam"):
                    mask, ring = frame(e, *layer(e, sw, sh)[1:])
                    if mask: add(e, "mask", mask)
                    if ring: add(e, "ring", ring)
            inp = {(eid, role): n for n, (eid, role, _) in enumerate(pngs, 1)}
            for e in subs_all:
                if on(e): shutil.copy(pick_font(e.get("font"))[1], tmp)
            for i, c in enumerate([c for c in clips if c.get("on", True)], 1):
                cel = clip_elements(elements, c)
                keep = kept(float(c["a"]), float(c["b"]), c.get("cut", []))
                if not keep: raise RuntimeError(f"Кліп {i} вирізано повністю")
                a, b, net = keep[0][0], keep[-1][1], sum(e - s for s, e in keep)
                ca = float(c["a"]); stem = base = f"{name} {int(ca // 60):02d}-{int(ca % 60):02d}"
                while stem in used: stem = f"{base} ({len([u for u in used if u.startswith(base)]) + 1})"
                used.add(stem); JOB.update(i=i, pct=0.0); dst = out / f"{stem}.mp4"
                if subs: Path(tmp, "subs.ass").write_text(subs_ass([q for q in cues if q["b"] > a and q["a"] < b], keep, subs_all), "utf-8")
                inputs = [x for _, role, p in pngs for x in ["-loop", "1", *(["-t", f"{b - a:.3f}"] if role == "mask" else []), "-i", p]]  # alphamerge не завершиться з нескінченною маскою
                parts = music_parts(cel, net)
                inputs += [x for path, off, _, length, *_ in parts for x in ["-ss", f"{off:.3f}", "-t", f"{length + .1:.3f}", "-i", path]]
                vel = next((e for e in elements if e["type"] == "video"), {}); vvol = float(vel.get("vol", 1))
                main = ("ca" if len(keep) > 1 else "am" if na > 1 else "0:a") if na else None
                afx, alabel = audio_filter(main, parts, 1 + len(pngs), vvol, net) if parts or vvol != 1 else ([], None)
                p = subprocess.Popen([ffbin("ffmpeg"), "-y", "-v", "error", "-nostats", "-progress", "pipe:1", *HW,
                                      "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src, *inputs,
                                      "-filter_complex", ";".join([build_filter(sw, sh, cel, keep, na, inp, sizes, bool(subs)), *afx]),
                                      "-map", "[v]", "-map", f"[{alabel}]" if alabel else "[ca]" if len(keep) > 1 and na else "[am]" if na > 1 else "0:a?", *args,
                                      "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=tmp, **SP)
                for line in p.stdout:
                    if line.startswith("out_time_us=") and line[12:].strip().isdigit():
                        JOB["pct"] = min(1.0, int(line[12:]) / 1e6 / net)
                if p.wait(): raise RuntimeError(p.stderr.read()[-600:])
                thumb = THUMBS / f"{rec['id']}_{i:02d}.jpg"
                run([ffbin("ffmpeg"), "-y", "-v", "error", "-ss", "1", "-i", str(dst), "-frames:v", "1", "-vf", "scale=270:-2", str(thumb)])
                rec["files"].append(dict(path=str(dst), thumb=str(thumb), a=float(c["a"]), b=float(c["b"]), len=net)); save_rec()
    except Exception as e: JOB["err"] = str(e)
    finally: JOB["running"] = False

# ── системні дії ──
def ask_file(kind):
    flt = {"video": ("Відео|*.mp4;*.mov;*.mkv;*.webm;*.flv;*.ts", "*.mp4 *.mov *.mkv *.webm *.flv *.ts"),
           "audio": ("Музика|*.mp3;*.wav;*.m4a;*.ogg;*.flac;*.aac;*.opus", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.opus")}.get(
          kind, ("Зображення|*.png;*.jpg;*.jpeg;*.webp;*.bmp", "*.png *.jpg *.jpeg *.webp *.bmp"))
    if os.name == "nt":                                            # системний діалог Windows без tkinter
        ps = ("Add-Type -AssemblyName System.Windows.Forms;"
              # невидимий власник «поверх усіх»: фоновий процес не може вивести діалог наперед, а власник-topmost — може
              "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false;Opacity=0;StartPosition='CenterScreen'};"
              "$o.Show();$o.Activate();"
              f"$d=New-Object System.Windows.Forms.OpenFileDialog;$d.Filter='{flt[0]}|Усі|*.*';"
              "if($d.ShowDialog($o) -eq 'OK'){[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($d.FileName))}")
        r = run(["powershell", "-NoProfile", "-STA", "-EncodedCommand", base64.b64encode(ps.encode("utf-16-le")).decode()])
        out = r.stdout.decode("ascii", "ignore").strip()                # base64 — кирилиця в шляху не ламається
        return base64.b64decode(out).decode("utf-8") if out else ""
    import tkinter as tk; from tkinter import filedialog
    t = tk.Tk(); t.withdraw(); t.attributes("-topmost", True)
    p = filedialog.askopenfilename(parent=t, filetypes=[(kind, flt[1]), ("*", "*.*")]); t.destroy(); return p

# ── публікація: опис від локального ШІ, відправка через Buffer ──
AI = localai.LocalAI(DATA / "ollama", OLLAMA, lambda *a: report_as("ai", *a), SP)
BUFFER = publish.Buffer(DATA / "buffer.json")
MEDIA = publish.WorkerMedia()
# ── оновлення з GitHub: що змінилось між нашим тегом і новим релізом, видно з порівняння комітів ──
LINKS = {"patreon": "https://www.patreon.com/miishanii"}             # підтримка автора; програма безкоштовна повністю
REPO, VERSION = "mrbear22/ShortsMaker", "1.7.3"                     # VERSION — тег релізу без «v»
RUNTIME_PATHS = ("build.sh", "installer.iss", "launcher/")           # змінилось це — потрібен новий інсталятор, інакше досить нових файлів з app/
UPDATE = {}

def github(path, raw=False):
    url = f"https://raw.githubusercontent.com/{REPO}/{path}" if raw else f"https://api.github.com/repos/{REPO}/{path}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ShortsMaker"}), timeout=30) as r:
        return r.read() if raw else json.load(r)

def check_update():
    if not PACKAGED: return                                         # із сорсів не оновлюємось
    try:
        rel = github("releases/latest"); tag = rel["tag_name"]; num = lambda v: tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())
        if num(tag) <= num(VERSION): return
        setup = next(a["browser_download_url"] for a in rel["assets"] if a["name"].lower().endswith(".exe"))
        try: files = github(f"compare/v{VERSION}...{tag}")["files"]
        except Exception: files = None                              # нашого тегу немає — лише інсталятором
        full = files is None or any(f["filename"].startswith(RUNTIME_PATHS) for f in files)
        UPDATE.update(version=tag.lstrip("v"), tag=tag, setup=setup, kind="full" if full else "app",
                      files=[f for f in files or [] if f["filename"].startswith("app/")])
    except Exception as e: print(datetime.now(), "update check:", ascii(e))

def apply_update():
    """'app' — файли з app/ вже замінено (беремо їх з репозиторію на тезі релізу); 'full' — шлях до інсталятора."""
    u, say = UPDATE, lambda frac: report("update", f"Завантажую версію {UPDATE['version']}", frac)
    if u.get("kind") == "full":
        dst = TMP / f"ShortsMaker-Setup-{u['version']}.exe"
        with urllib.request.urlopen(urllib.request.Request(u["setup"], headers={"User-Agent": "ShortsMaker"}), timeout=60) as r, open(dst, "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(256 * 1024): f.write(chunk); got += len(chunk); say(got / total if total else None)
        return dst
    new = {}
    for i, f in enumerate(u["files"]):                               # спершу все завантажити, потім підмінити — без напівоновленої програми
        if f["status"] != "removed": new[f["filename"][4:]] = github(f"{u['tag']}/{f['filename']}", raw=True)
        say((i + 1) / len(u["files"]))
    for f in u["files"]:
        for old in (f.get("previous_filename"), f["filename"] if f["status"] == "removed" else None):
            if old and old.startswith("app/"): (HERE / old[4:]).unlink(missing_ok=True)
    for name, data in new.items(): (HERE / name).write_bytes(data)
    return None

def render_files(p, path):
    """Записи готового шорту в історії рендерів проєкту (той самий файл міг рендеритись кілька разів)."""
    return [f for r in p["renders"] for f in r["files"] if f["path"] == path]

def clip_caption(pid, path):
    p = load_project(pid); f = next(iter(render_files(p, path)), None)
    if not f: raise ValueError("Шорт не знайдено в проєкті")
    a, b = f["a"], f["b"]; source = p["name"] or Path(p["video"]).stem
    why = next((c.get("why", "") for c in p["clips"] if abs(c["a"] - a) < .05 and abs(c["b"] - b) < .05), "")
    speech = " ".join(q["text"] for q in p["cues"] if q["b"] > a and q["a"] < b)
    if not speech and Path(p["video"]).is_file():                 # реплік немає — транскрипт (кешується на диску)
        speech = " ".join(t for t, s, e in transcript(p["video"], a, b, "")[1])
    return publish.caption(source, why, speech, OLLAMA, ollama_model())

def save_post(pid, path, post):
    def put(p):
        for f in render_files(p, path): f["post"] = {**f.get("post", {}), **post}
    update_project(pid, put)

def unqueue(pid, path):
    """Повернути шорт до редагування: прибрати його пости з черги Buffer і забути статус (посилання на відео лишається)."""
    f = next(iter(render_files(load_project(pid), path)), None)
    if not f: raise ValueError("Шорт не знайдено в проєкті")
    left = {}
    for cid, rec in f.get("post", {}).get("buffer", {}).items():
        if not rec.get("id"): continue
        try: BUFFER.delete_post(rec["id"])
        except Exception as e: left[cid] = rec; err = str(e)[:200]
    save_post(pid, path, {"buffer": left})
    if left: raise RuntimeError(err)
    return {}

def publish_batch(pid, plan, privacy):
    """Кожен шорт — у свої канали (вибрані на картці) на свій час; результат пишемо в проєкт, щоб бачити статус."""
    threading.Thread(target=cleanup_media, daemon=True).start()     # заодно прибрати вже опубліковане
    chans = {c["id"]: c for c in BUFFER.channels()}; p = load_project(pid); ok, errors = 0, []; t0 = time.time()
    for i, item in enumerate(plan):
        n = f" {i + 1} з {len(plan)}" if len(plan) > 1 else ""
        say = lambda frac, i=i, n=n: report("upload", f"Викладаю відео{n}", (i + frac) / len(plan), t0)
        say(0)
        f = next(iter(render_files(p, item["path"])), None)
        if not f: errors.append("файл не знайдено"); continue
        post, sent = f.get("post", {}), {}
        try: url = media_url(pid, f, say)
        except Exception as e: errors.append(str(e)[:200]); save_post(pid, f["path"], {"buffer": {**post.get("buffer", {}), "_media": dict(error=str(e)[:200])}}); continue
        for cid in item.get("channels", []):
            try: r = BUFFER.create_post(chans[cid], publish.post_text(post), post.get("title", ""), item["dueAt"], url, privacy); sent[cid] = dict(id=r["id"], dueAt=item["dueAt"]); ok += 1
            except Exception as e: sent[cid] = dict(error=str(e)[:200]); errors.append(str(e)[:200])
        save_post(pid, f["path"], {"buffer": {k: v for k, v in {**post.get("buffer", {}), **sent}.items() if k != "_media"}})
    report("", "")
    return dict(ok=ok, errors=len(errors), first_error=errors[0] if errors else "")

MEDIA_KEEP_S = 2 * 86400                                          # після запланованого часу відео ще дві доби лежить у сховищі: Buffer буває спізнюється

def cleanup_media():
    """Прибрати зі сховища відео, які Buffer уже опублікував: місце безкоштовне лише до 10 ГБ."""
    for p in projects():
        for r in p["renders"]:
            for f in r["files"]:
                post = f.get("post", {}); u = post.get("mediaUrl", "")
                sent = [x for x in post.get("buffer", {}).values() if x.get("id")]
                if u and sent and all(datetime.fromisoformat(x["dueAt"].replace("Z", "+00:00")).timestamp() < time.time() - MEDIA_KEEP_S for x in sent):
                    MEDIA.delete(u); save_post(p["id"], f["path"], {"mediaUrl": "", "mediaStamp": ""})

def media_url(pid, f, progress=lambda frac: None):
    """Публічне посилання на файл шорту: викладаємо один раз, далі беремо збережене (поки файл той самий і лежить у нашому сховищі)."""
    post, stamp = f.get("post", {}), f"{os.path.getsize(f['path'])}:{os.path.getmtime(f['path'])}"
    if MEDIA.base and post.get("mediaUrl", "").startswith(MEDIA.base) and post.get("mediaStamp") == stamp: return post["mediaUrl"]   # старі посилання catbox — у смітник
    name = uuid.uuid5(uuid.NAMESPACE_URL, f["path"] + stamp).hex[:24] + ".mp4"
    url = MEDIA.upload(f["path"], name, progress)
    save_post(pid, f["path"], {"mediaUrl": url, "mediaStamp": stamp}); f.setdefault("post", {}).update(mediaUrl=url, mediaStamp=stamp)
    return url

def reveal(path):
    if os.name == "nt": subprocess.Popen(["explorer", "/select,", path] if Path(path).is_file() else ["explorer", path])
    else: subprocess.Popen(["xdg-open", str(Path(path).parent if Path(path).is_file() else path)])

def allowed_files():
    s = set(PICKED) | {str(p) for p in MIXES.glob("*.m4a")} | {str(p) for p in MIXES.glob("*.mp4")}
    for p in projects():
        s |= {p["video"]} | {e[k] for e in p["elements"] for k in ("preview", "logo", "path") if e.get(k)} | {m["path"] for m in p.get("music", [])}
        s |= {r["out"] for r in p["renders"]} | {f[k] for r in p["renders"] for f in r["files"] for k in ("path", "thumb")}
    return s

# ── HTTP ──
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def send_file(self, path):
        if not path or not Path(path).is_file(): return self.reply({"error": "нема файлу"}, code=404)
        size = os.path.getsize(path); m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        a, b = (int(m[1] or 0), int(m[2]) if m[2] else size - 1) if m else (0, size - 1)
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", {".mp4": "video/mp4", ".mov": "video/mp4", ".webm": "video/webm", ".m4a": "audio/mp4", ".png": "image/png",
                                          ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
                         .get(Path(path).suffix.lower(), "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", b - a + 1)
        if m: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(a); left = b - a + 1
                while left > 0 and (chunk := f.read(min(1 << 20, left))): self.wfile.write(chunk); left -= len(chunk)
        except OSError: pass

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/": return self.reply((HERE / "ui.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/publish.js": return self.reply((HERE / "publish.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/api/state": return self.reply(dict(cfg=CFG, job=JOB))
            if u.path == "/api/status": return self.reply(dict(JOB, tasks=TASKS, ffmpeg=not PACKAGED or (FFDIR / "ffmpeg.exe").is_file()))
            if u.path == "/api/version": return self.reply(dict(version=CODE_VERSION, app=VERSION, boot=STARTED))
            if u.path == "/api/update": return self.reply(dict(current=VERSION, version=UPDATE.get("version")))
            if u.path == "/api/fonts": _fonts_ready.wait(30); return self.reply(list(FONTS))
            if u.path == "/api/projects":
                ps = projects()
                for p in ps:
                    for r in p["renders"]:
                        for f in r["files"]: f["exists"] = Path(f["path"]).is_file()
                return self.reply(ps)
            if u.path == "/api/project": return self.reply(load_project(q["id"]))
            if u.path == "/api/ai": return self.reply(dict(model=ollama_model(), setup=AI.setup_state, can_setup=AI.can_setup(), size_gb=5))
            if u.path == "/api/buffer":
                if not BUFFER.key: return self.reply(dict(connected=False))
                return self.reply(dict(connected=True, channels=BUFFER.channels()))
            if u.path == "/api/brands": return self.reply({k: dict(name=n, color=c, path=d) for k, (n, c, d) in brands.BRANDS.items()})
            if u.path == "/api/media": return self.reply(dict(connected=bool(MEDIA.base)))
            if u.path == "/api/buffer/schema": return self.reply(BUFFER.schema_summary())
            if u.path == "/api/buffer/queue": return self.reply(dict(posts=BUFFER.scheduled()))
            if u.path == "/api/peaks": return self.reply(peaks(q["p"]))
            if u.path == "/api/audio":                            # тривалість музичного файлу
                r = run([ffbin("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", q["p"]])
                return self.reply(dict(dur=float(r.stdout.decode().strip() or 0)))
            if u.path == "/api/probe":
                sw, sh, dur, na = probe(q["p"]); return self.reply(dict(sw=sw, sh=sh, dur=dur, region=REGION, tracks=na, mix=preview_mix(q["p"], na), play=preview_video(q["p"])))
            if u.path == "/file": return self.send_file(q.get("p") if q.get("p") in allowed_files() else "")
            self.reply({"error": "404"}, code=404)
        except Exception as e: self.reply({"error": str(e)}, code=500)

    def do_POST(self):
        p = urlparse(self.path).path
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        CUR.task = d.get("task")                                  # потік обслуговує й інші запити: ключ задаємо щоразу
        try:
            if p == "/api/ping": PAGES[d.get("page", "?")] = time.time(); return self.reply({})
            if p == "/api/open":                                  # лише відомі адреси: сторінка не може відкрити довільне посилання
                if url := LINKS.get(d.get("link")): webbrowser.open(url)
                return self.reply({})
            if p == "/api/bye":                                   # вікно закрили: останнє — виходимо одразу
                known = PAGES.pop(d.get("page", "?"), None)       # невідоме вікно — сторінка до перезапуску після оновлення
                if known and not PAGES: threading.Thread(target=quit_app, daemon=True).start()
                return self.reply({})
            if p == "/api/config":
                CFG.update({k: v for k, v in d.items() if k in CFG and k not in ("project", "defaults")}); save_cfg(); return self.reply(CFG)
            if p == "/api/pick":
                if f := ask_file(d["kind"]): PICKED.add(f)
                return self.reply(dict(path=f))
            if p == "/api/project/new":
                pr = new_project(); CFG["project"] = pr["id"]; save_cfg(); return self.reply(pr)
            if p == "/api/project/open": load_project(d["id"]); CFG["project"] = d["id"]; save_cfg(); return self.reply({})
            if p == "/api/project/save":
                keys = ("name", "video", "region", "clips", "elements", "cues", "scan", "music")
                pr = update_project(d["id"], lambda pr: pr.update({k: d[k] for k in keys if k in d}))
                if "elements" in d: CFG["defaults"] = d["elements"]; save_cfg()        # новий проєкт почне з цих налаштувань
                return self.reply(dict(updated=pr["updated"]))
            if p == "/api/project/delete":
                for r in load_project(d["id"])["renders"]:
                    for f in r["files"]: Path(f["thumb"]).unlink(missing_ok=True)
                proj_file(d["id"]).unlink()
                if CFG["project"] == d["id"]: CFG["project"] = ""; save_cfg()
                return self.reply({})
            if p == "/api/element":
                img, w, h = art(d); buf = io.BytesIO(); img.save(buf, "PNG")
                return self.reply(dict(w=w, h=h, pad=PAD, img="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()))
            if p == "/api/analyze":
                report("", ""); f = features(d["video"], d.get("region"))
                clips = []
                if d.get("suggest", True):                            # лише крива без пошуку моментів — мову не розпізнаємо
                    segs = transcript(d["video"], *f["region"], d.get("lang", ""))[1] if CFG["stt"] and f["audio"] else []
                    m = safe_ollama_model() if segs else None              # ШІ нічого не дав — звичайні моменти за рухом і звуком
                    clips = (ai_moments(f, segs, m) if m else []) or with_context(suggest(f), segs)
                return self.reply(dict(dur=f["dur"], sw=f["sw"], sh=f["sh"], step=B, region=f["region"], curve=np.round(f["ex"], 2).tolist(),
                                       clips=clips, speed=CFG["speed"]))
            if p == "/api/subs":                                  # кілька звукових доріжок (OBS) — кожна окремим спікером
                a0, a1 = d["region"]; report("", ""); na = probe(d["video"])[3]; cues = []
                for sp, track in enumerate(range(na) if na > 1 else [None]):
                    words = transcript(d["video"], a0, a1, d.get("lang", ""), track, f"Розпізнаю доріжку {sp + 1} з {na}" if na > 1 else "Розпізнаю мову")[0]
                    cues += [dict(c, sp=sp) for c in make_cues(words, max(1, int(d.get("words", 3))))]
                return self.reply(dict(cues=sorted(cues, key=lambda c: c["a"]), tracks=max(1, na), speed=CFG["speed"]))
            if p == "/api/update/apply":
                setup = apply_update()
                threading.Thread(target=finish_update, args=(setup,), daemon=True).start()
                return self.reply(dict(kind="full" if setup else "app"))
            if p == "/api/buffer/key": BUFFER.set_key(d.get("key", "")); return self.reply(dict(connected=bool(BUFFER.key)))
            if p == "/api/ai/setup": AI.begin_setup(); return self.reply(AI.setup_state)
            if p == "/api/caption": return self.reply(clip_caption(d["id"], d["path"]))
            if p == "/api/post/save": save_post(d["id"], d["path"], d["post"]); return self.reply({})
            if p == "/api/post/unqueue": return self.reply(unqueue(d["id"], d["path"]))
            if p == "/api/publish": return self.reply(publish_batch(d["id"], d["plan"], d.get("privacy", "public")))
            if p == "/api/detect_cam": return self.reply(dict(rect=detect_cam(d["video"])))
            if p == "/api/render":
                if JOB["running"]: return self.reply(JOB, code=409)
                update_project(d["id"], lambda pr: pr.update(clips=d["clips"], elements=d["elements"], cues=d["cues"], music=d.get("music", [])))
                JOB.update(running=True, i=0, n=sum(c.get("on", True) for c in d["clips"]), pct=0.0, err="", out="",
                           id=uuid.uuid4().hex[:10], project=d["id"])
                threading.Thread(target=render, args=(d["id"], d["clips"], d["elements"], d["cues"]), daemon=True).start()
                return self.reply(JOB)
            if p == "/api/reveal":
                if d["path"] not in allowed_files(): return self.reply({"error": "заборонено"}, code=403)
                reveal(d["path"]); return self.reply({})
            self.reply({"error": "404"}, code=404)
        except Exception as e: self.reply({"error": str(e)}, code=500)
        finally:
            if CUR.task: TASKS.pop(CUR.task, None)              # операція скінчилась — рядок поступу зникає

def open_window(url):
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        edge = Path(base or "-", "Microsoft/Edge/Application/msedge.exe")
        if edge.is_file():                                         # вікно-застосунок без панелей браузера
            return subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={DATA / 'window'}", "--no-first-run",
                                     "--no-default-browser-check", "--window-size=1500,950"], env=SYS_ENV)
    webbrowser.open(url)

PAGE_SILENT_S = 150                                               # вікно, що зникло без «бувай» (браузер вбили): згорнуте браузер будить рідко, тож чекаємо довше

def quit_app():
    """Вікна немає — виходимо повністю, разом з рендером, ffmpeg і локальним ШІ: без вікна користувачеві це вже не потрібно."""
    AI.stop()
    if os.name == "nt": run(["taskkill", "/F", "/T", "/PID", str(os.getpid())])   # /T — з усіма дочірніми процесами
    os._exit(0)

def watchdog():                                                    # запасний шлях: звичайне закриття вікна обробляє /api/bye миттєво
    while True:
        time.sleep(1); now = time.time()
        for k, t in list(PAGES.items()):
            if now - t > PAGE_SILENT_S: PAGES.pop(k, None)
        if not PAGES and now - STARTED > 60: quit_app()               # при старті даємо вікну хвилину відкритись

def detached(*cmd):
    """Процес, що переживе цей: не дочірній (через start), тож taskkill /T у quit_app його не зачепить."""
    subprocess.Popen(["cmd", "/c", "start", "", *cmd], creationflags=0x08000000)   # CREATE_NO_WINDOW

def finish_update(setup):
    """Код замінено — запускаємо нову версію без нового вікна (сторінка перезавантажиться сама) і виходимо.
    Потрібен інсталятор — закриваємо вікно й ставимо тихо; інсталятор сам відкриє програму."""
    time.sleep(.5)                                                # відповідь має дійти до сторінки
    if setup: run(["powershell", "-NoProfile", "-Command",
                   f"Get-CimInstance Win32_Process -Filter \"name='msedge.exe'\" | ? {{ $_.CommandLine -like '*{str(DATA / 'window')}*' }} | % {{ Stop-Process -Id $_.ProcessId -Force }}"])
    if setup: detached(str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    else: detached(str(ROOT / "runtime" / "pythonw.exe"), str(HERE / "shorts.py"), "--restart")
    time.sleep(1.5)                                               # cmd має встигнути запустити процес і вийти, інакше taskkill /T забере і його
    if setup: quit_app()                                          # інсталятор сам відкриє програму
    AI.stop(); STT.stop(); os._exit(0)                            # без taskkill /T: вікно Edge — наш дочірній процес, воно лишається й перезавантажиться

def reopen_window(url):
    """Старе вікно не озвалось після оновлення (його закрила попередня версія) — відкриваємо нове."""
    time.sleep(8)
    if not PAGES and (w := open_window(url)): threading.Thread(target=watch_window, args=(w,), daemon=True).start()

def watch_window(proc):
    """Процес вікна Edge завершився — вікно закрили. Якщо він вийшов за секунди, це не наше вікно: Edge передав його вже запущеному."""
    t0 = time.time(); proc.wait()
    if time.time() - t0 > 5: quit_app()

CODE_VERSION = uuid.uuid5(uuid.NAMESPACE_URL, "".join(f.read_text("utf-8") for f in sorted(HERE.glob("*.*")) if f.suffix in (".py", ".html", ".js"))).hex[:12]   # будь-який файл програми

def port_owner(port):
    """PID процесу, що слухає порт (Windows)."""
    m = re.search(rf"127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)", run(["netstat", "-ano", "-p", "TCP"], text=True).stdout)
    return int(m.group(1)) if m else None

def stop_old_server(url):
    """На порту інша версія ShortsMaker, що не рендерить, — зупиняємо її, щоб оновлення почало працювати одразу.
    True, якщо зупинили; False — лишаємо як є (та сама версія, йде рендер, чужа програма або не Windows)."""
    get = lambda path: json.loads(urllib.request.urlopen(url + path, timeout=3).read())
    try: busy = get("/api/status")["running"]
    except Exception: return False                              # порт зайняв не ShortsMaker
    try: same = get("/api/version").get("version") == CODE_VERSION
    except Exception: same = False                              # версії до цієї не знають /api/version
    pid = None if same or busy or os.name != "nt" else port_owner(CFG["port"])
    if not pid or pid == os.getpid(): return False
    print(datetime.now(), "stopping old version, PID", pid); return run(["taskkill", "/F", "/T", "/PID", str(pid)]).returncode == 0   # /T — разом з її локальним ШІ

class Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"    # на Windows SO_REUSEADDR дає зайняти чужий порт: новий запуск «стартував», а відповідав старий

def bind(tries=1):
    for i in range(tries):
        try: return Server(("127.0.0.1", CFG["port"]), Handler)
        except OSError: time.sleep(.25 * (i < tries - 1))
    return None

def prepare_ffmpeg():
    global HW
    CUR.task = "ffmpeg"                                           # рядок поступу, який інтерфейс показує сам
    try:
        if pick_encoder()[0] != "cpu": HW = ["-hwaccel", "auto"]
    except Exception as e: print(datetime.now(), "ffmpeg:", ascii(e))
    finally: TASKS.pop("ffmpeg", None)

def main():
    CFG.update(rd(CFG_FILE, {})); migrate()
    url = f"http://127.0.0.1:{CFG['port']}"
    srv = bind(tries=40) if "--restart" in sys.argv else bind() or (stop_old_server(url) and bind(tries=20))   # після оновлення стара версія сама звільняє порт
    if not srv: return open_window(url)                           # вже запущено (та сама версія або рендерить) — просто відкрити вікно
    threading.Thread(target=scan_fonts, daemon=True).start()
    threading.Thread(target=prepare_ffmpeg, daemon=True).start()   # перший запуск: ffmpeg завантажується, поки відкривається вікно
    print(datetime.now(), "start", url)
    threading.Thread(target=check_update, daemon=True).start()
    if "--restart" in sys.argv:                                   # після оновлення: старе вікно перезавантажиться саме
        threading.Thread(target=watchdog, daemon=True).start(); threading.Thread(target=reopen_window, args=(url,), daemon=True).start()
    elif "--no-window" not in sys.argv:
        threading.Thread(target=watchdog, daemon=True).start()
        if w := open_window(url): threading.Thread(target=watch_window, args=(w,), daemon=True).start()
    srv.serve_forever()

if __name__ == "__main__":
    if "--stt-worker" in sys.argv: stt_worker(sys.argv[sys.argv.index("--stt-worker") + 1])
    else: main()
