"""Локальний ШІ для описів і пошуку моментів: портативна Ollama в data/ollama.
Завантажується сама один раз, коли вперше знадобиться (як модель розпізнавання мови); встановлена в системі Ollama теж підходить."""
import json, os, shutil, subprocess, threading, time, urllib.request, zipfile
from pathlib import Path

OLLAMA_VERSION = "v0.40.16"                                         # закріплена версія: структура архіву не зміниться під ногами
OLLAMA_ZIP = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-windows-amd64.zip"
AI_MODEL = "gemma3:4b"                                              # 3.3 ГБ, добре пише українською
NEED_FREE_GB = 8                                                    # архів 1.6 ГБ + розпакування + модель
START_WAIT_S = 20


class LocalAI:
    def __init__(self, home: Path, url: str, report, popen_flags: dict, fetch):
        self.home, self.url, self.report, self.flags = home.resolve(), url, report, popen_flags   # відносний OLLAMA_MODELS Ollama відкидає
        self.fetch = fetch                                          # завантаження зі спробами: повільний інтернет не обриває
        self.proc, self.lock = None, threading.Lock()
        self.setup_state = dict(running=False, err="")

    @property
    def exe(self): return self.home / "ollama.exe"

    def can_setup(self): return os.name == "nt"

    def installed(self):
        """Моделі запущеної Ollama ([{name, size, …}]) або None, якщо вона не відповідає."""
        try:
            with urllib.request.urlopen(self.url + "tags", timeout=1) as r: return json.load(r)["models"]
        except (OSError, ValueError): return None

    def model(self):
        """Модель для роботи: найбільша встановлена; портативну Ollama запускаємо, якщо вона вже завантажена."""
        ms = self.installed()
        if ms is None and self.exe.is_file() and not self.setup_state["running"]: self.start(); ms = self.installed()   # під час розпакування — не чіпати
        return max(ms, key=lambda m: m["size"])["name"] if ms else None

    def chat(self, model, prompt, timeout, **options):
        """Відповідь моделі — JSON-об'єкт."""
        body = dict(model=model, stream=False, format="json", options=options, messages=[{"role": "user", "content": prompt}])
        with urllib.request.urlopen(urllib.request.Request(self.url + "chat", json.dumps(body).encode()), timeout=timeout) as r:
            return json.loads(json.load(r)["message"]["content"])

    def start(self):
        with self.lock:
            if self.proc and self.proc.poll() is None: return
            env = dict(os.environ, OLLAMA_MODELS=str(self.home / "models"), OLLAMA_HOST=self.url.split("//")[1].split("/")[0])
            self.proc = subprocess.Popen([str(self.exe), "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **self.flags)
        for _ in range(START_WAIT_S * 4):
            if self.installed() is not None: return
            time.sleep(.25)
        raise RuntimeError("Локальний ШІ не запустився")

    def stop(self):
        if self.proc and self.proc.poll() is None: self.proc.kill()

    # ── перше налаштування: у фоні, з поступом для інтерфейсу ──
    def begin_setup(self):
        if self.setup_state["running"] or self.model(): return
        if not self.can_setup(): raise RuntimeError("Автоматично — лише на Windows. Встанови Ollama з ollama.com")
        self.setup_state.update(running=True, err="")
        threading.Thread(target=self._setup, daemon=True).start()

    def _setup(self):
        try:
            if not self.exe.is_file(): self._download()
            self.start()
            if not self.installed(): self._pull(AI_MODEL)
        except Exception as e: self.setup_state["err"] = str(e)
        finally: self.setup_state["running"] = False; self.report("", "")

    def _download(self):
        self.home.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.home).free < NEED_FREE_GB * 1e9:
            raise RuntimeError(f"Замало місця на диску: для ШІ потрібно ~{NEED_FREE_GB} ГБ вільних")
        tmp, t0 = self.home / "ollama.zip.part", time.time()
        self.fetch(OLLAMA_ZIP, tmp, lambda done, total: self.report("ai", f"Завантажую ШІ, {total / 1e9:.1f} ГБ", done / total if total else None, t0))
        self.report("ai", "Розпаковую локальний ШІ…", None)
        with zipfile.ZipFile(tmp) as z: z.extractall(self.home)
        tmp.unlink()

    def _pull(self, name):
        body, t0, layers = json.dumps({"model": name, "stream": True}).encode(), time.time(), {}
        with urllib.request.urlopen(urllib.request.Request(self.url + "pull", body), timeout=3600) as r:
            for line in r:
                s = json.loads(line)
                if s.get("error"): raise RuntimeError("Модель: " + s["error"])
                if s.get("total"): layers[s.get("digest", "")] = (s.get("completed", 0), s["total"])
                done, total = sum(c for c, _ in layers.values()), sum(t for _, t in layers.values())
                self.report("ai", f"Завантажую модель ШІ, {total / 1e9:.1f} ГБ", done / total if total else None, t0)
