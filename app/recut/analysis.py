"""Пошук моментів: рух і звук, контекст фраз, локальний ШІ."""
import time
from datetime import datetime
import numpy as np
from . import localai
from .core import B, CFG, check, DATA, ev, FPS_A, HOOK_LEN, HOOK_W, learn, OLLAMA, REGION, report, SP, STT_LOCK, TASK, waiting, WIN, z
from .media import all_audio, ff, probe, stamp, stop
from .net import fetch
from .twitch import local_input
from .stt import transcript

# ── аналіз моментів ──
def analyze_video(inp, sw, sh, length, t0):
    aw = 160; ah = ev(aw * sh / sw)
    p = ff(*inp, "-vf", f"fps={FPS_A},scale={aw}:{ah},format=gray", "-f", "rawvideo")
    prev, mot = None, []
    try:
        while len(buf := p.stdout.read(aw * ah)) == aw * ah:
            f = np.frombuffer(buf, np.uint8).reshape(ah, aw).astype(np.int16)
            mot.append(np.abs(f - (f if prev is None else prev)).mean()); prev = f
            if len(mot) % 25 == 0: report("scan", "Аналіз руху й звуку", min(.99, 0.9 * len(mot) / FPS_A / length), t0)   # звук — решта ~10 %
    finally: stop(p)
    mot = np.array(mot) if mot else np.zeros(1)
    return mot, np.where(mot > max(20, 5 * np.median(mot)))[0] / FPS_A

def analyze_audio(inp, nb, na):
    sr = 8000; k = int(sr * B)
    p, raw = ff(*inp, "-vn", *all_audio(na), "-ac", "1", "-ar", str(sr), "-f", "s16le"), bytearray()
    try:
        while chunk := p.stdout.read(1 << 20): raw += chunk; check()
    finally: stop(p)
    a = np.frombuffer(bytes(raw), np.int16).astype(np.float32)
    if a.size < k: return np.zeros(nb)
    db = 10 * np.log10((a[:a.size // k * k].reshape(-1, k) ** 2).mean(1) + 1)
    return np.pad(db, (0, max(0, nb - len(db))), mode="edge")[:nb]

_FEAT = {}
def features(src, region):
    """Ознаки області [a0, a1] (None — перші REGION с); час усередині — від a0."""
    sw, sh, dur, audio = probe(src)
    a0, a1 = region or (0, REGION); a1 = min(float(a1), dur); a0 = max(0.0, min(float(a0), a1 - 1))
    key = (src, stamp(src), a0, a1)
    if key not in _FEAT:
        nb = max(1, int((a1 - a0) / B)); t0 = time.time()
        inp = local_input(src, "low", a0, a1, lambda f: report("scan", "Завантажую з Twitch", min(.99, f), t0))   # файл — одразу; Twitch — шматки паралельно
        mot, cuts = analyze_video(inp, sw, sh, a1 - a0, time.time()); db = analyze_audio(inp, nb, audio); learn("scan", a1 - a0, t0)
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

# ── контекст моментів через локальну LLM (Ollama, безкоштовно; якщо не запущена — за фразами транскрипту) ──
PROMPT = """Ти вирізаєш вірусні вертикальні шорти з довгого відео чи стріму.
Рядки транскрипту — "[початок-кінець] текст", час у секундах. Раптові гучні моменти (сміх, крики, реакції) на: {peaks}.
Обери до {n} найсмішніших чи найзахопливіших завершених моментів. Кожен кліп триває {lo}-{hi} с, починається там, де починається
потрібний контекст (підводка), і закінчується одразу після панчлайну чи реакції.
Відповідай лише JSON: {{"clips": [{{"start": сек, "end": сек, "score": 1-10, "why": "коротко українською: що відбувається і чим цікаво"}}]}}

{lines}"""

def safe_ollama_model():
    """Модель локального ШІ або None (портативна Ollama стартує сама, якщо вже завантажена)."""
    try: return AI.model()
    except Exception as e: print(datetime.now(), "local AI unavailable:", ascii(e)); return None

LLM_TIMEOUT, LLM_TRIES = 180, 2                                   # завислий ШІ не тримає аналіз; збій — ще одна спроба

def ask_llm(model, prompt):
    """Кандидати від ШІ для одного вікна; збій чи сміття у відповіді — порожньо (аналіз не падає)."""
    for attempt in range(LLM_TRIES):
        try:
            with STT_LOCK: raw = waiting(AI.chat, model, prompt, LLM_TIMEOUT, temperature=0, seed=0, num_ctx=16384).get("clips", [])   # не разом з Whisper: ділять відеокарту
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
    learn("llm", a1 - a0, t0)
    out = []
    for c in sorted(cand, key=lambda c: -c["score"]):
        a = max(a0, c["start"]); b = min(max(c["end"], a + lo), a + hi, a1)
        if b - a >= 1 and not any(a < o["b"] and b > o["a"] for o in out): out.append(dict(a=a, b=b, why=str(c.get("why", ""))[:200]))
        if len(out) == n: break
    return sorted(out, key=lambda c: c["a"])

# ── публікація через Buffer; локальний ШІ — для пошуку моментів ──
AI = localai.LocalAI(DATA / "ollama", OLLAMA, lambda *a: TASK.show("ai", *a), SP, fetch)

def analyze(video, region, find_moments, lang):
    """Крива цікавості області й моменти: за змістом мови (локальний ШІ), інакше — за рухом і звуком з фразами навколо."""
    report("", ""); f = features(video, region); clips = []
    if find_moments:                                               # лише крива без пошуку моментів — мову не розпізнаємо
        segs = transcript(video, *f["region"], lang)[1] if CFG["stt"] and f["audio"] else []
        m = safe_ollama_model() if segs else None                  # ШІ нічого не дав — звичайні моменти за рухом і звуком
        clips = (ai_moments(f, segs, m) if m else []) or with_context(suggest(f), segs)
    return dict(dur=f["dur"], sw=f["sw"], sh=f["sh"], step=B, region=f["region"], curve=np.round(f["ex"], 2).tolist(), clips=clips, speed=CFG["speed"])
