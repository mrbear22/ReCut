"""Місце на диску: скільки займає кеш і моделі, очищення."""
from .analysis import AI, _FEAT
from .core import DATA, MIXES, MODELS, TRANS, WAVES
from .media import FAILED, PEAKS
from .stt import STT

# місце на диску: що можна прибрати без шкоди — завантажиться чи порахується знову, коли знадобиться
STORE = [("view", "Кеш перегляду", lambda: [DATA / "hls", MIXES, WAVES]), ("speech", "Розпізнана мова", lambda: [TRANS]),
         ("models", "Моделі розпізнавання мови", lambda: [MODELS, DATA / "hf"]), ("ai", "Локальний ШІ для пошуку моментів", lambda: [DATA / "ollama"])]

def dir_size(d): return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.is_dir() else 0

def storage(): return [dict(key=k, name=n, size=sum(map(dir_size, dirs()))) for k, n, dirs in STORE]

def clear_store(key):
    """Прибрати категорію. Зайняті зараз файли (відео, що грає) лишаються — без помилки."""
    if key == "models": STT.stop()                               # процес розпізнавання тримає модель відкритою
    if key == "ai": AI.stop()
    for d in dict((k, dirs) for k, _, dirs in STORE)[key]():
        for f in sorted(d.rglob("*"), key=lambda x: -len(x.parts)) if d.is_dir() else []:
            try: f.unlink() if f.is_file() else f.rmdir()
            except OSError: pass
    PEAKS.clear(); _FEAT.clear(); FAILED.clear()
    return storage()
