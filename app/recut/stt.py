"""Розпізнавання мови: окремий процес faster-whisper, кеш точних відрізків, репліки."""
import base64, json, os, re, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path
import numpy as np
from concurrent.futures import ThreadPoolExecutor, wait as wait_any
from difflib import SequenceMatcher
from .core import Cancelled, CFG, CHUNK, DATA, HERE, learn, MODELS, report, run, SP, STT_LOCK, STT_MODELS, sttm, TMP, TRANS, waiting
from .libs import fetch_cuda, has_cuda_libs, libs_missing, need_libs, STT_LIBS
from .media import all_audio, ffbin, peaks, probe, stamp
from .twitch import local_input

# ── розпізнавання мови — в окремому процесі: збій відеокарти (скидання драйвера) вбиває лише його, а не всю програму ──
class SttWorker:
    def __init__(self): self.proc, self.device, self.model, self.gpu_failures = None, None, None, 0

    def alive(self): return self.proc is not None and self.proc.poll() is None

    def start(self, device, model):
        exe = Path(sys.executable); py = exe.with_name("python.exe") if exe.with_name("python.exe").is_file() else exe   # pythonw не дає stdout
        self.model = model
        self.proc = subprocess.Popen([str(py), str(HERE / "shorts.py"), "--stt-worker", device, model], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(DATA / "stt.log", "a", encoding="utf-8"), **SP)
        self.device = device
        try: msg = waiting(self.read)
        except Cancelled: self.stop(); raise                       # скасували під час завантаження моделі — процес геть разом із ним
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
        except Cancelled: self.stop(); raise                       # процес ще дописує відповідь — новий почне з чистого
        finally: job.unlink(missing_ok=True)

STT = SttWorker()

def model_dirs(model): return [d for d in MODELS.glob(f"models--*faster-whisper-{model}") if d.is_dir()]

def prepare_stt(model, want_cuda):
    """Перший раз: бібліотеки, одразу за ними модель — і водночас бібліотеки NVIDIA; один рядок поступу на все.
    Скасували — недокачане докачається у фоні й знадобиться наступного разу."""
    loading = not any(f for d in model_dirs(model) for f in d.rglob("model.bin"))
    part = {"libs": [.2e9, 0.0], "model": [STT_MODELS[model] if loading else 0, 0.0], "cuda": [1.3e9 if want_cuda else 0, 0.0]}
    mark = lambda k: lambda f: part[k].__setitem__(1, f)
    def libs_and_model():
        need_libs(STT_LIBS, "faster_whisper", "", "stt", say=mark("libs")); part["libs"][1] = 1
        if loading:                                                # модель — тим самим huggingface_hub, що й процес розпізнавання, у ту ж теку
            from faster_whisper.utils import download_model        # бібліотека з'являється лише щойно, рядком вище
            download_model(model, cache_dir=str(MODELS)); part["model"][1] = 1
    def cuda():
        try: fetch_cuda(say=mark("cuda"))
        except Exception as e: print("CUDA не завантажено, розпізнаю на процесорі:", ascii(e))   # без інтернету чи PyPI змінився — повільніше, але працює
        part["cuda"][1] = 1
    ex, t0 = ThreadPoolExecutor(2), time.time(); futs = [ex.submit(libs_and_model)] + ([ex.submit(cuda)] if want_cuda else [])
    size = sum(w for w, _ in part.values())
    try:
        while not all(f.done() for f in futs):
            if loading and part["libs"][1] >= 1: part["model"][1] = min(.99, sum(f.stat().st_size for d in model_dirs(model) for f in d.rglob("*") if f.is_file()) / STT_MODELS[model])
            report("stt", f"Завантажую розпізнавання мови, {size / 1e9:.1f} ГБ", min(.99, sum(w * f for w, f in part.values()) / size), t0)
            wait_any(futs, timeout=1)
        for f in futs: f.result()
    finally: ex.shutdown(wait=False)

def start_worker(model):
    """Процес розпізнавання: відеокарта — дві спроби (скидання драйвера буває разовим), далі процесор; двічі впала — до перезапуску лише процесор."""
    import ctranslate2                                             # з бібліотек, що качаються, коли вперше знадобились
    gpu = ctranslate2.get_cuda_device_count() > 0 and STT.gpu_failures < 2 and has_cuda_libs()
    for dev in ["cuda"] * max(0, 2 - STT.gpu_failures) * gpu + ["cpu"]:
        try: STT.start(dev, model); return STT
        except (RuntimeError, ChildProcessError) as e:
            print(datetime.now(), "stt:", dev, "недоступно:", ascii(e)); STT.gpu_failures += dev == "cuda"
    raise RuntimeError("Розпізнавання мови не запускається")

def stt_model():
    """Бібліотеки, CUDA й модель — один раз; далі процес розпізнавання, що вже завантажив модель."""
    model = sttm()
    if STT.alive() and STT.model == model: return STT
    STT.stop()                                                     # обрали іншу модель — інший процес
    nvidia = os.name == "nt" and Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvcuda.dll").is_file()   # драйвер NVIDIA — видно й без бібліотек
    want_cuda = nvidia and STT.gpu_failures < 2 and not has_cuda_libs()
    if libs_missing(STT_LIBS) or want_cuda or not any(f for d in model_dirs(model) for f in d.rglob("model.bin")): prepare_stt(model, want_cuda)
    return start_worker(model)

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

def stt_worker(device, model):
    """Окремий процес: модель у пам'яті, завдання — рядки JSON у stdin, відповіді — у stdout."""
    out, sys.stdout = sys.stdout, sys.stderr                  # сторонні print-и бібліотек не ламають протокол
    send = lambda m: (out.write(json.dumps(m) + "\n"), out.flush())
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel(model, device=device, compute_type="float16" if device == "cuda" else "int8", download_root=str(MODELS))
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

def whisper(src, t0, t1, lang, tick, na, track=None):
    """Відрізок [t0, t1) -> слова й речення з абсолютним часом: [текст, початок, кінець]; tick(с розпізнано).
    track — одна звукова доріжка (окремий спікер), None — усі зведені."""
    audio = ["-map", f"0:a:{track}"] if track is not None else all_audio(na)
    r = run([ffbin("ffmpeg"), "-v", "error", *local_input(src, "low", t0, min(t1, probe(src)[2]), lambda f: report("stt", "Завантажую звук з Twitch", f)),
             "-vn", *audio, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    if r.returncode: raise RuntimeError("Аудіо для розпізнавання: " + r.stderr.decode("utf-8", "replace")[-300:])
    words, sg = [], []
    for text, a, b, ws in stt_run(r.stdout, lang, tick):
        sg.append([text, t0 + a, t0 + b]); words += [[w, t0 + wa, t0 + wb] for w, wa, wb in ws]
    return dict(words=words, segs=sg, len=len(r.stdout) / 32000)

STT_PAD = 1.5                                                      # запас по краях відрізка, щоб не різати слова навпіл

def transcript(src, a0, a1, lang, track=None, label="Розпізнаю мову"):
    """(слова, речення) в [a0, a1]. Розпізнаємо лише те, чого ще немає в кеші: кеш пам'ятає точні відрізки, а не 5-хвилинні шматки."""
    na = probe(src)[3]                                         # зведені доріжки й кожна окремо — різний кеш
    tag = uuid.uuid5(uuid.NAMESPACE_URL, f"{src}|{stamp(src)}|{sttm()}|{lang}" + (f"|track{track}" if track is not None else f"|mix{na}" * (na > 1))).hex[:16]
    store = TRANS / f"{tag}.json"
    with STT_LOCK:
        pieces = json.loads(store.read_text("utf-8")) if store.is_file() else []
        for f in TRANS.glob(f"{tag}_*.json"):                      # кеш старих версій: шматки по CHUNK с від k·CHUNK
            k = int(f.stem.rsplit("_", 1)[1]); t = json.loads(f.read_text("utf-8")); pieces.append(dict(a=k * CHUNK, b=k * CHUNK + t["len"], words=t["words"], segs=t["segs"], old=1))
        gaps = [(a0, a1)]
        for p in pieces:                                           # мінус уже розпізнане
            gaps = [g for x, y in gaps for g in ((x, min(y, p["a"])), (max(x, p["b"]), y)) if g[1] - g[0] > .5]
        gaps = [(x + i * CHUNK, min(y, x + (i + 1) * CHUNK)) for x, y in gaps for i in range(int(np.ceil((y - x) / CHUNK)))]   # довге — шматками, з поступом
        if gaps:
            stt_model(); t0, total, done = time.time(), sum(y - x for x, y in gaps), 0.0
            for g0, g1 in gaps:
                tick = lambda s: report("stt", label, min(.99, (done + s) / total), t0); tick(0)
                t = whisper(src, max(0, g0 - STT_PAD), g1 + STT_PAD, lang, tick, na, track)
                core = lambda x: g0 <= (x[1] + x[2]) / 2 < g1      # із запасом по краях беремо лише своє: на стику з сусіднім відрізком — без повторів
                pieces.append(dict(a=g0, b=g1, words=[w for w in t["words"] if core(w)], segs=[x for x in t["segs"] if core(x)]))
                store.write_text(json.dumps([p for p in pieces if not p.get("old")], ensure_ascii=False), "utf-8"); done += g1 - g0
            learn("stt", done, t0)
    inside = lambda x: x[2] > a0 and x[1] < a1
    words = sorted({w[1]: w for p in pieces for w in p["words"] if inside(w)}.values(), key=lambda w: w[1])
    segs = sorted({x[1]: x for p in pieces for x in p["segs"] if inside(x)}.values(), key=lambda x: x[1])
    return words, segs

def phrases(words, n):
    """Слова -> фрази субтитрів: до n слів, розрив на паузі чи кінці речення."""
    out = []
    for w in words:
        if out and len(out[-1]) < n and w[1] - out[-1][-1][2] < 0.5 and not out[-1][-1][0].endswith((".", "!", "?", "…")): out[-1].append(w)
        else: out.append([w])
    return out

def copies(video, na):
    """Доріжки, що повторюють одну з попередніх (OBS часто пише ту саму суміш на кілька доріжок): вдруге їх не розпізнаємо."""
    report("stt", "Порівнюю звукові доріжки", None)
    env = [np.frombuffer(base64.b64decode(peaks(video, t)["b64"]), np.uint8).astype(np.float32) for t in range(na)]   # гучність — та сама, що для хвилі
    dup = set()
    for j in range(1, na):
        for i in range(j):
            n = min(len(env[i]), len(env[j]))
            if i not in dup and n > 50 and env[i][:n].std() and env[j][:n].std() and np.corrcoef(env[i][:n], env[j][:n])[0, 1] > .97: dup.add(j); break
    return dup

def drop_echo(tracks):
    """Та сама фраза на двох доріжках (суміш і окремо мікрофон): слово лишається на доріжці, де слів менше, — це доріжка самого мовця."""
    norm = lambda s: re.sub(r"\W+", "", s.lower())
    seen, out = {}, [None] * len(tracks)
    for k in sorted(range(len(tracks)), key=lambda k: len(tracks[k])):
        out[k] = [w for w in tracks[k] if not any(abs(t - w[1]) < .35 for t in seen.get(norm(w[0]), ()))]
        for w in out[k]: seen.setdefault(norm(w[0]), []).append(w[1])
    return out

def make_cues(words, n):
    """Доріжка субтитрів: фраза = репліка з часом кожного слова (k) для підсвітки."""
    ph = phrases(words, n)
    return [dict(a=p[0][1], b=min(p[-1][2] + 0.3, nx[0][1] if nx else 1e9), text=" ".join(w[0] for w in p), k=[w[1] for w in p])
            for p, nx in zip(ph, ph[1:] + [None])]

def align(words, text, a, b):
    """Текст, який ввів користувач, → час кожного його слова за розпізнаним звуком.
    Літери зіставляємо з розпізнаними (difflib): слово отримує час своєї першої збіглої літери; слова без збігу — між сусідами.
    Повертає (частка збіглих літер, k)."""
    norm = lambda s: re.sub(r"\W+", "", s.lower())
    rc, rt = "", []                                                # розпізнані літери та час кожної
    for w, wa, wb in words:
        n = norm(w); rc += n; rt += [wa + (wb - wa) * i / len(n) for i in range(len(n))]
    us = [norm(w) for w in text.split()]; starts = [sum(map(len, us[:i])) for i in range(len(us))]; uc = "".join(us)
    at = {}
    for i, j, n in SequenceMatcher(None, uc, rc, autojunk=False).get_matching_blocks():
        for d in range(n): at[i + d] = rt[j + d]
    k = [next((at[c] for c in range(s, s + len(u)) if c in at), None) for u, s in zip(us, starts)]
    for i, t in enumerate(k):                                      # незбіглі — рівно між найближчими відомими (або краями репліки)
        if t is not None: continue
        l = next((j for j in range(i - 1, -1, -1) if k[j] is not None), None); r = next((j for j in range(i + 1, len(k)) if k[j] is not None), None)
        lt, rt_ = (k[l] if l is not None else a), (k[r] if r is not None else b); lo = -1 if l is None else l; hi = len(k) if r is None else r
        k[i] = lt + (rt_ - lt) * (i - lo) / (hi - lo)
    out = []
    for t in k: out.append(min(b, max(a, t, out[-1] if out else a)))   # у межах репліки й по порядку
    return len(at) / max(1, len(uc)), out

def realign(video, a, b, text, lang):
    """Час слів відредагованої репліки за звуком цього відрізка: розпізнане береться з кешу, бракує — розпізнаємо лише його.
    Кілька доріжок (окремі мовці) — беремо ту, з якою текст збігається найкраще."""
    na = probe(video)[3]
    return max((align(transcript(video, a, b, lang, t, "Підганяю слова до звуку")[0], text, a, b) for t in ([None] if na < 2 else range(na))), key=lambda r: r[0])[1]

def subtitles(video, spans, lang, words):
    """Репліки для відрізків. Кілька звукових доріжок (OBS) — кожна окремим спікером; доріжка-копія чи лише чуже відлуння — не спікер."""
    report("", ""); na = probe(video)[3]
    tracks = [t for t in range(na) if t not in copies(video, na)] if na > 1 else [None]; per = []
    for n, track in enumerate(tracks):
        label = f"Розпізнаю доріжку {n + 1} з {len(tracks)}" if len(tracks) > 1 else "Розпізнаю мову"
        ws = {w[1]: w for a0, a1 in spans for w in transcript(video, a0, a1, lang, track, label)[0]}
        per.append(sorted(ws.values(), key=lambda w: w[1]))
    per = [ws for ws in drop_echo(per) if ws] or [[]]
    cues = [dict(c, sp=sp) for sp, ws in enumerate(per) for c in make_cues(ws, max(1, int(words)))]
    return dict(cues=sorted(cues, key=lambda c: c["a"]), tracks=len(per), speed=CFG["speed"])
