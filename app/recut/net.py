"""Завантаження: повтори, багатопотокові шматки (Range), перекачка з поступом."""
import http.client, json, threading, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .core import report

class KeyedLocks:
    """Замок на кожен ключ: те саме двічі не качаємо, різне — одночасно."""
    def __init__(self): self._locks, self._guard = {}, threading.Lock()

    def __call__(self, key):
        with self._guard: return self._locks.setdefault(key, threading.Lock())

NET_TRIES, NET_TIMEOUT = 5, 20                                    # мережа буває повільна чи рветься: 20 с тиші — нове з'єднання, кілька спроб
PART_MIN, PARTS = 32 << 20, 8                                      # великий файл — кількома з'єднаннями одразу
NET_FAILED = "Завантаження не вдалося: інтернет повільний чи переривається. Спробуй ще раз — уже завантажене не качатиметься знову"

def retrying(attempt, what):
    """attempt() до NET_TRIES разів: обрив чи завислий сервер — пауза й ще раз; відмова сервера (4xx) — одразу помилка."""
    for i in range(NET_TRIES):
        try: return attempt()
        except (OSError, http.client.HTTPException, ValueError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500: raise RuntimeError(f"{Path(urllib.parse.urlsplit(what).path).name}: {e}") from e
            print(datetime.now(), "download", i + 1, what, ascii(e))
            if i == NET_TRIES - 1: raise RuntimeError(NET_FAILED) from e
            time.sleep(3 * (i + 1))

def open_url(url, first=None, last=None):
    """З'єднання; first/last — лише ці байти (Range)."""
    headers = {"User-Agent": "ReCut", **({"Range": f"bytes={first}-{last}"} if first is not None else {})}
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=NET_TIMEOUT)

def pump(r, writers, progress=lambda got, total: None):
    """Відповідь сервера → кожному writer шматками по 64 КБ; менше, ніж обіцяв Content-Length, — обрив."""
    total, got = int(r.headers.get("Content-Length") or 0), 0
    while chunk := r.read(1 << 16):
        for w in writers: w(chunk)
        got += len(chunk); progress(got, total)
    if total and got < total: raise OSError(f"обрив: {got} з {total} байтів")

def fetch_parts(url, dst, size, progress):
    """Файл шматками по з'єднанню на кожен (Range); обірваний шматок — далі з місця обриву. False — сервер шматків не дає."""
    step, got = -(-size // PARTS), [0] * PARTS
    with open(dst, "wb") as f: f.truncate(size)
    def attempt(i):
        first, last = i * step + got[i], min(size, (i + 1) * step) - 1
        with open_url(url, first, last) as r, open(dst, "r+b") as f:
            if r.status != 206: return False
            f.seek(first); pump(r, [f.write, lambda c: got.__setitem__(i, got[i] + len(c))], lambda *_: progress(sum(got), size))
        return True
    with ThreadPoolExecutor(PARTS) as ex: return all(ex.map(lambda i: retrying(lambda: attempt(i), url), range(PARTS)))

def fetch(url, dst=None, progress=lambda got, total: None, raw=False):
    """Файл з інтернету (dst) або відповідь (без dst): JSON, а з raw — байти. Великий файл — кількома з'єднаннями. progress(отримано, розмір)."""
    if dst is None: return retrying(lambda: (lambda r: r.read() if raw else json.load(r))(open_url(url)), url)
    def attempt(whole=False):
        with open_url(url) as r:
            size, final = int(r.headers.get("Content-Length") or 0), r.url
            if whole or size < PART_MIN or r.headers.get("Accept-Ranges", "").lower() != "bytes":
                with open(dst, "wb") as out: return pump(r, [out.write], progress)
        return fetch_parts(final, dst, size, progress) or attempt(whole=True)   # адреса після переадресацій; сервер шматків не дав — одним з'єднанням
    retrying(attempt, url)

def download(url, dst, text, stage):
    t0 = time.time()
    fetch(url, dst, lambda got, total: report(stage, text, got / total if total else None, t0))
