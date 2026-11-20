"""Спільне: шляхи, налаштування, рядки поступу й скасування, дрібні помічники."""
import json, os, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
import numpy as np

"""ReCut — горизонтальне відео / стрім -> вертикальні шорти.
GUI відкривається вікном Edge (або в браузері). Дані: ../data (портативно) або ./data.
"""

HERE = Path(__file__).resolve().parent.parent                      # тека програми (app), пакет recut — у ній
PACKAGED = (HERE.parent / "runtime").is_dir()                    # зібрана програма (інсталятор); інакше — запуск із сорсів
ROOT = HERE.parent if PACKAGED else HERE
DATA = Path(os.environ["RECUT_DATA"]) if os.environ.get("RECUT_DATA") else ROOT / "data"   # RECUT_DATA — окрема тека даних (тести)
THUMBS, TRANS, PROJ, MODELS, MIXES, WAVES = DATA / "thumbs", DATA / "transcripts", DATA / "projects", DATA / "models", DATA / "mixes", DATA / "waves"
TMP, RENDERS, CUDA, LIBS, FFDIR = DATA / "tmp", ROOT / "renders", ROOT / "data" / "cuda", ROOT / "data" / "libs", ROOT / "ffmpeg"   # завантажені бібліотеки — спільні
sys.path.insert(0, str(LIBS))                                      # бібліотеки, завантажені, коли вперше знадобились
for d in (THUMBS, TRANS, PROJ, MODELS, MIXES, WAVES, TMP, RENDERS): d.mkdir(parents=True, exist_ok=True)
# портативно: тимчасові файли й кеш моделей — лише в теці програми, ніде більше в системі
SYS_ENV = dict(os.environ)                                         # для вікна Edge: його тимчасові файли не мають жити в нашій теці (їх тримає BITS і програму не видалити)
tempfile.tempdir = str(TMP); os.environ.update(TMP=str(TMP), TEMP=str(TMP), HF_HOME=str(DATA / "hf"), HF_HUB_DISABLE_TELEMETRY="1")
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

CFG_FILE = DATA / "settings.json"
CANVAS = (1080, 1920)                                             # полотно за замовчуванням (9:16); проєкт може мати своє
CFG = dict(n_clips=8, min_len=20, max_len=50, encoder="auto", quality=21, stt=False, stt_model="large-v3-turbo", stt_lang="", sub_words=3, project="", twitch_channel="", port=8765, lang="",
           speed=dict(scan=5.0, stt=10.0, llm=20.0, render=1.0))   # секунд відео за секунду роботи; уточнюється після кожного запуску
HOOK_LEN, HOOK_W, FPS_A, B = 3, 2.0, 5, 0.5
REGION, CHUNK, WIN = 1800, 300, 600    # область аналізу за замовчуванням; шматок транскрипції в кеші; вікно транскрипту на запит LLM, с
STT_MODELS, OLLAMA = {"large-v3-turbo": 1.62e9, "large-v3": 3.09e9}, "http://127.0.0.1:11434/api/"   # модель розпізнавання -> розмір
sttm = lambda: CFG.get("stt_model") if CFG.get("stt_model") in STT_MODELS else "large-v3-turbo"
PAD = 40                                       # поле під тінь навколо плашки
ENC = {"nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "{q}", "-b:v", "0", "-pix_fmt", "yuv420p"],
       "amf":   ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "{q}", "-qp_p", "{q}", "-pix_fmt", "yuv420p"],
       "qsv":   ["-c:v", "h264_qsv", "-preset", "slow", "-global_quality", "{q}", "-pix_fmt", "nv12"],
       "cpu":   ["-c:v", "libx264", "-preset", "medium", "-crf", "{q}", "-pix_fmt", "yuv420p"]}
HW = []
LOCK, STT_LOCK, PICKED = threading.Lock(), threading.Lock(), set()
z = lambda x: (x - np.median(x)) / (x.std() + 1e-6)
ev = lambda v: max(2, int(round(v / 2)) * 2)
rd = lambda p, default: json.loads(p.read_text("utf-8")) if p.is_file() else default
save_cfg = lambda: CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=2), "utf-8")
on = lambda e: e.get("on", True)

class Cancelled(Exception): """Користувач натиснув «Скасувати»."""

class HttpError(Exception):
    """Відповідь інтерфейсу з кодом 4xx: запит неможливий (рендер уже йде, файл не з проєкту…)."""
    def __init__(self, code, msg): super().__init__(msg); self.code = code

class Tasks:
    """Довгі операції: рядок поступу на кожну (ключ задає інтерфейс у запиті), скасування й поточна операція цього потоку."""
    def __init__(self): self.rows, self.cancelled, self._here = {}, set(), threading.local()

    @property
    def current(self): return getattr(self._here, "task", None)

    def begin(self, task): self._here.task = task

    def finish(self, task):
        """Операція скінчилась: рядок поступу зникає, позначка «скасовано» — теж."""
        self.rows.pop(task, None); self.cancelled.discard(task)

    def cancel(self, task): self.cancelled.add(task)

    def check(self):
        """Скасували поточну операцію — перериваємо її (довгі цикли питають це разом із поступом)."""
        if self.current in self.cancelled: raise Cancelled()

    def show(self, task, stage, text, frac=None, t0=None):
        """Етап, частка й скільки лишилось за швидкістю, з якою етап іде зараз. Порожній етап — операцію почато заново."""
        if not stage: self.rows.pop(task, None); return
        el = time.time() - t0 if t0 else 0
        self.rows[task] = dict(stage=stage, text=text, frac=frac, eta=el * (1 - frac) / frac if frac and frac > .03 and t0 else None)

    def report(self, stage, text, frac=None, t0=None): self.check(); self.show(self.current or "other", stage, text, frac, t0)

TASK = Tasks()
report, check = TASK.report, TASK.check                            # короткі назви для довгих циклів

def waiting(fn, *a, **kw):
    """Довгий виклик, якого не перервати зсередини (запит до ШІ): чекаємо у фоні й тим часом перевіряємо, чи не скасували."""
    out = {}
    def go():
        try: out["r"] = fn(*a, **kw)
        except BaseException as e: out["e"] = e
    th = threading.Thread(target=go, daemon=True); th.start()
    while th.is_alive(): th.join(.25); check()
    if "e" in out: raise out["e"]
    return out["r"]

def learn(kind, media_s, t0):
    if media_s > 5: CFG["speed"][kind] = round(media_s / max(.1, time.time() - t0), 2); save_cfg()

def run(args, **kw): return subprocess.run(args, capture_output=True, **SP, **kw)

is_url = lambda s: str(s).startswith(("http://", "https://"))

_enc = {}

CODE_VERSION = uuid.uuid5(uuid.NAMESPACE_URL, "".join(f.read_text("utf-8") for f in sorted([*HERE.glob("*.*"), *(HERE / "recut").glob("*.py"), *(HERE / "js").glob("*.js")]) if f.suffix in (".py", ".html", ".js", ".css"))).hex[:12]   # будь-який файл програми
