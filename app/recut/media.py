"""ffmpeg: пошук і завантаження, проба файлу, кодування з поступом, копії для перегляду, хвилі звуку."""
import base64, json, os, shutil, subprocess, threading, urllib.error, urllib.parse, urllib.request, uuid, zipfile
from datetime import datetime
from pathlib import Path
import numpy as np
from .core import _enc, CFG, ENC, FFDIR, HW, is_url, MIXES, PACKAGED, run, SP, TASK, TMP, WAVES
from .libs import LIB_LOCKS
from .net import download
from .twitch import hls_index, hls_path, vod

def ff(*a): return subprocess.Popen([ffbin("ffmpeg"), "-v", "error", *HW, *a, "-"], stdout=subprocess.PIPE, **SP)

def stop(p):
    if p.poll() is None: p.kill()
    p.wait()

def encode(args, length, tick, **kw):
    """ffmpeg з поступом: tick(секунд готово) на кожному кроці; tick може скасувати — тоді ffmpeg зупиняється."""
    p = subprocess.Popen([ffbin("ffmpeg"), "-y", "-v", "error", "-nostats", "-progress", "pipe:1", *HW, *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **SP, **kw)
    try:
        for line in p.stdout:
            if line.startswith("out_time_us=") and line[12:].strip().isdigit(): tick(min(length, int(line[12:]) / 1e6))
        if p.wait(): raise RuntimeError(p.stderr.read()[-600:])
    finally: stop(p)

def probe(src):
    """(ширина, висота, тривалість, скільки звукових доріжок)"""
    if is_url(src): v = vod(src); return v["w"], v["h"], v["dur"], 1
    j = json.loads(subprocess.check_output([ffbin("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                            "-of", "json", src], **SP))
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"], float(j["format"]["duration"]), sum(s["codec_type"] == "audio" for s in j["streams"])

def amix(n, out):
    """Фільтр, що зводить усі n звукових доріжок (OBS пише гру й мікрофон окремо) в одну [out]."""
    return "".join(f"[0:a:{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0[{out}]"

def all_audio(n):
    return [] if n < 2 else ["-filter_complex", amix(n, "a"), "-map", "[a]"]

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
stamp = lambda src: f"twitch:{vod(src)['id']}" if is_url(src) else os.path.getmtime(src)   # для кешу: запис Twitch — його номер, файл — час зміни
preview_key = lambda src: uuid.uuid5(uuid.NAMESPACE_URL, f"{src}|{stamp(src)}").hex[:16]

def preview_mix(src, n):
    """Зведений звук для прев'ю (браузер грає лише першу доріжку)."""
    return (prepared(MIXES / f"{preview_key(src)}.m4a", ["-i", src, "-vn", *all_audio(n), "-c:a", "aac", "-b:a", "160k"]) or "") if n > 1 else ""

def container(src):
    return subprocess.check_output([ffbin("ffprobe"), "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0", src], **SP, text=True).strip()

PROXIES_KEPT = 3                                                    # копії займають місце як оригінал — тримаємо лише останні
def preview_video(src):
    """Браузер не грає MPEG-TS, FLV, AVI навіть з H.264 усередині (так часто зберігаються записи Twitch):
    для прев'ю — копія в MP4 без перекодування; рендер бере оригінал. Запис Twitch — плейлист через наш проксі."""
    if is_url(src): return "/hls?u=" + urllib.parse.quote(vod(src)["view"], safe="")
    if any(f in container(src) for f in ("mp4", "webm")): return src
    out = MIXES / f"{preview_key(src)}.mp4"
    if not out.is_file():
        for old in sorted((f for f in MIXES.glob("*.mp4") if ".tmp" not in f.name), key=os.path.getmtime)[:-(PROXIES_KEPT - 1) or None]: old.unlink(missing_ok=True)
    p = prepared(out, ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-c", "copy"])
    return src if p is None else p
def pick_encoder():
    key = (CFG["encoder"], CFG["quality"])
    if key not in _enc:
        for k in ([CFG["encoder"]] if CFG["encoder"] != "auto" else ENC):
            if k == "cpu" or run([ffbin("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                                  *ENC[k][:2], "-f", "null", "-"]).returncode == 0:
                _enc[key] = k, [x.format(q=CFG["quality"]) for x in ENC[k]]; break
    return _enc[key]

# ── важке завантажується, коли вперше знадобиться: ffmpeg одразу після першого запуску, решта — під свою дію ──
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"   # з libass для субтитрів

def ffmpeg_ready(): return not PACKAGED or (FFDIR / "ffmpeg.exe").is_file()   # у зібраній програмі ffmpeg качається при першому запуску

def ffbin(name):
    """Шлях до ffmpeg/ffprobe. У зібраній програмі перший виклик завантажує ffmpeg у теку програми."""
    if not PACKAGED: return name                                   # із сорсів — той, що в PATH
    exe = FFDIR / f"{name}.exe"
    with LIB_LOCKS("ffmpeg"):
        if not exe.is_file():
            z = TMP / "ffmpeg.zip"; download(FFMPEG_URL, z, "Завантажую ffmpeg, 90 МБ", "ffmpeg")
            part = FFDIR.with_name("ffmpeg.part"); shutil.rmtree(part, ignore_errors=True); part.mkdir()
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():
                    if "/bin/" in n and n.lower().endswith((".exe", ".dll")) and not n.lower().endswith("ffplay.exe"): (part / Path(n).name).write_bytes(zf.read(n))
            shutil.rmtree(FFDIR, ignore_errors=True); part.rename(FFDIR); z.unlink(missing_ok=True)   # тека з'являється лише цілою
    return str(exe)

def source(src, kind):
    """Що читати ffmpeg: файл як є; із запису Twitch — плейлист якості під задачу (low — рух, audio — звук і мова, mid — вебкамера, best — рендер)."""
    return vod(src)[kind] if is_url(src) else src

PEAKS = {}
PEAK_STEP = 40                                                     # відліків звуку на одне значення хвилі

def loudness(data, rate, args):
    """Найгучніший відлік у кожному біні (0–128): звук з байтів data (або з args -i ...) у u8."""
    raw = np.frombuffer(run([ffbin("ffmpeg"), "-v", "error", *args, "-vn", "-ac", "1", "-ar", str(rate * PEAK_STEP), "-f", "u8", "-"], input=data).stdout, np.uint8)
    n = len(raw) // PEAK_STEP
    return (np.abs(raw[:n * PEAK_STEP].astype(np.int16) - 128).reshape(n, PEAK_STEP).max(1) if n else np.zeros(0)).astype(np.uint8)

def wave(v, rate, t0=0.0):
    top = float(np.percentile(v, 99.5)) if len(v) else 0             # поодинокі піки не стискають решту хвилі
    return dict(rate=rate, t0=t0, b64=base64.b64encode(np.clip(v.astype(np.float32) * 255 / (top or 1), 0, 255).astype(np.uint8).tobytes()).decode())

def segment_loudness(f, init, rate):
    """Гучність шматка Twitch з кешу; рахується раз — лишається у WAVES, навіть коли сам шматок з кешу викинуто."""
    out = WAVES / f"{f.stem}_{rate}.u8"
    if out.is_file(): return np.frombuffer(out.read_bytes(), np.uint8)
    v = loudness((init.read_bytes() if init else b"") + f.read_bytes(), rate, ["-i", "pipe:0"])
    tmp = out.with_suffix(f".{uuid.uuid4().hex}"); tmp.write_bytes(v.tobytes()); tmp.replace(out); return v

def twitch_peaks(src, rate):
    """Хвиля запису Twitch — лише з уже скачаних шматків (перегляд, аналіз, субтитри): качати весь звук заради неї не варто.
    Решта — тиша, поки її не переглянули."""
    v, have = np.zeros(int(vod(src)["dur"] * rate) + 1, np.uint8), np.zeros(int(vod(src)["dur"] * rate) + 1, bool)
    for kind in ("view", "low"):
        init, parts = hls_index(src, kind); ini = init and hls_path(init)
        if ini and not os.path.exists(ini): continue                      # fMP4 без init-шматка не розібрати
        for t, d, u in parts:
            i, f = int(t * rate), hls_path(u)
            if have[i:i + int(d * rate)].all() or not (os.path.exists(WAVES / f"{f.stem}_{rate}.u8") or os.path.exists(f)): continue
            try: s = segment_loudness(f, ini, rate)[:len(v) - i]
            except OSError: continue                                 # кеш саме прибрав шматок або його тримає інша програма
            v[i:i + len(s)] = np.maximum(v[i:i + len(s)], s); have[i:i + len(s)] = True
    if not have.any(): return dict(rate=rate, t0=0, b64="")
    a, b = np.flatnonzero(have)[[0, -1]]; return wave(v[a:b + 1], rate, a / rate)

def peaks(path, track=None, rate=50):
    """Гучність для хвилі на таймлайні: rate значень на секунду від t0, 0–255, base64. track — одна звукова доріжка відео.
    Довге відео рахується один раз: результат лежить на диску."""
    if is_url(path): return twitch_peaks(path, rate)
    key = uuid.uuid5(uuid.NAMESPACE_URL, f"{path}|{os.path.getmtime(path)}|{track}|{rate}").hex[:16]; f = WAVES / f"{key}.json"
    if key not in PEAKS:
        if f.is_file(): PEAKS[key] = json.loads(f.read_text("utf-8"))
        else: PEAKS[key] = wave(loudness(None, rate, ["-i", path, *(["-map", f"0:a:{track}"] if track is not None else [])]), rate); f.write_text(json.dumps(PEAKS[key]), "utf-8")
    return PEAKS[key]

def prepare_ffmpeg():
    TASK.begin("ffmpeg")                                           # рядок поступу, який інтерфейс показує сам
    try:
        if pick_encoder()[0] != "cpu": HW[:] = ["-hwaccel", "auto"]   # список той самий: модулі, що його імпортували, бачать зміну
    except Exception as e: print(datetime.now(), "ffmpeg:", ascii(e))
    finally: TASK.finish("ffmpeg")

def duration(path):
    """Тривалість файлу (музика), с; 0 — не прочиталось."""
    r = run([ffbin("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(r.stdout.decode().strip() or 0)
