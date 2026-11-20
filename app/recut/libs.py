"""Бібліотеки, що качаються, коли вперше знадобляться: колеса з PyPI, NVIDIA."""
import importlib, os, re, time, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait as wait_any
from .core import CUDA, LIBS, TMP, cuda_dirs, report, use_cuda_dlls
from .net import KeyedLocks, fetch

# ── локальне розпізнавання мови (faster-whisper, як в AutoSubs) ──
# Програма легка: модель (1.6 ГБ) і, лише для відеокарт NVIDIA, CUDA-бібліотеки (1.9 ГБ) завантажуються один раз у data/
CUDA_PKGS = (("nvidia-cublas-cu12", ""), ("nvidia-cudnn-cu12", "9."), ("nvidia-cuda-nvrtc-cu12", ""))
STT_LIBS = ("faster-whisper==1.2.1 ctranslate2==4.9.0 onnxruntime==1.32.0 av==19.0.2 tokenizers==0.23.3 huggingface-hub==2.4.0 hf-xet==1.8.0 "
            "anyio==4.16.0 click==8.5.1 colorama==0.4.6 filelock==4.2.10 flatbuffers==25.12.19 fsspec==2026.9.0 h11==0.16.0 httpcore2==2.16.0 "
            "httpx2==2.16.0 idna==3.20 packaging==26.3 protobuf==7.36.2 pyyaml==6.0.3 tqdm==4.70.1 truststore==0.10.5 typing-extensions==4.16.0").split()
CV_LIBS = ["opencv-python-headless==4.14.0.94"]

LIB_LOCKS = KeyedLocks()

def parallel(jobs, say, n=4):
    """Завантаження паралельно (n з'єднань): jobs — [функція(поступ)], поступ кожної — частка 0…1; say(загальна частка) щопівсекунди.
    Скасували — не чекаємо недокачаного."""
    got = [0.0] * len(jobs); ex = ThreadPoolExecutor(n); futs = [ex.submit(j, lambda f, k=k: got.__setitem__(k, f)) for k, j in enumerate(jobs)]
    try:
        while not all(f.done() for f in futs): say(sum(got) / max(1, len(jobs))); wait_any(futs, timeout=.5)   # готово — одразу далі, без паузи
        return [f.result() for f in futs]
    finally: ex.shutdown(wait=False, cancel_futures=True)

def install_wheels(files, dest, stage, text, only=None, say=None):
    """Колеса з PyPI -> dest, по чотири паралельно; only — розпакувати лише файли з цим префіксом; say(частка) — замість власного рядка поступу."""
    dest.mkdir(exist_ok=True); total, t0 = max(1, sum(f["size"] for f in files)), time.time()
    jobs = [lambda p, f=f: fetch(f["url"], TMP / f["filename"], lambda got, _: p(got / total * len(files))) for f in files]   # частка — за байтами, не за файлами
    parallel(jobs, say or (lambda frac: report(stage, text, min(.99, frac), t0)))
    for f in files:
        whl = TMP / f["filename"]
        with zipfile.ZipFile(whl) as z: z.extractall(dest, [n for n in z.namelist() if n.startswith(only)] if only else None)
        whl.unlink()

def libs_missing(specs):
    """Яких коліс з точними версіями ще немає в data/libs: обірване завантаження лишає частину — докачуємо решту."""
    norm = lambda s: re.sub(r"[-_.]+", "_", s).lower()            # PyYAML-6.0.3 / pyyaml==6.0.3 → pyyaml_6_0_3
    have = {norm(p.name[:-len(".dist-info")]) for p in LIBS.glob("*.dist-info")} if LIBS.is_dir() else set()
    return [s for s in specs if norm(s.replace("==", "-")) not in have]

def need_libs(specs, module, text, stage="libs", say=None):
    """Колеса з PyPI (точні версії) -> data/libs, яких ще немає. Модуль, встановлений поза data/libs (запуск із сорсів), — не чіпаємо."""
    with LIB_LOCKS(module):
        missing = libs_missing(specs)
        if not missing: return
        spec = importlib.util.find_spec(module)
        if spec and LIBS not in Path(spec.origin or "-").parents: return
        wheel = lambda s: next(f for f in fetch(f"https://pypi.org/pypi/{s.replace('==', '/')}/json")["urls"] if f["filename"].endswith("none-any.whl") or
                               (f["filename"].endswith("win_amd64.whl") and re.search(r"-(cp312|cp3\d+-abi3|py3)-", f["filename"])))
        with ThreadPoolExecutor(8) as ex: files = list(ex.map(wheel, missing))   # описи пакетів — разом, а не по черзі
        install_wheels(files, LIBS, stage, text, say=say)         # dist-info — у тому ж архіві: є він, є й колесо
        importlib.invalidate_caches()

def has_cuda_libs(): return any(b.parent.name == "cublas" for b in cuda_dirs())   # бібліотеки NVIDIA вже є (завантажені чи встановлені)

def fetch_cuda(say=None):
    """Колеса nvidia-* з PyPI -> data/cuda. Без сторонніх модулів: качається разом з бібліотеками розпізнавання, а не після них."""
    tag = "win_amd64" if os.name == "nt" else "manylinux"
    num = lambda v: tuple(int(x) for x in v.split("."))           # лише випуски: 12.9.1.4, не 9.1.0rc1
    def wheel(pkg):
        name, ver = pkg; rel = fetch(f"https://pypi.org/pypi/{name}/json")["releases"]
        best = max((v for v, fs in rel.items() if v.startswith(ver) and re.fullmatch(r"[\d.]+", v) and any(tag in f["filename"] for f in fs)), key=num)
        return next(f for f in rel[best] if tag in f["filename"] and f["filename"].endswith(".whl"))
    with LIB_LOCKS("cuda"):
        if has_cuda_libs(): return
        with ThreadPoolExecutor(4) as ex: files = list(ex.map(wheel, CUDA_PKGS))
        install_wheels(files, CUDA, "stt", f"Завантажую бібліотеки NVIDIA, {sum(f['size'] for f in files) / 1e9:.1f} ГБ", only="nvidia/", say=say)
    use_cuda_dlls()
