"""Оновлення з релізів GitHub. Змінився лише код — завантажуємо app.zip (сотні КБ) і перезапускаємось;
змінився вбудований Python чи ffmpeg (RUNTIME) — завантажуємо інсталятор і ставимо тихо."""
import json, shutil, tempfile, urllib.request, zipfile
from pathlib import Path

REPO = "mrbear22/ShortsMaker"
VERSION = "1.0.0"
RUNTIME = 1                                                      # +1, коли міняється runtime, ffmpeg чи ShortsMaker.exe: тоді потрібен інсталятор
APP_FILES = ("shorts.py", "publish.py", "localai.py", "update.py", "ui.html", "publish.js")
UA = {"User-Agent": "ShortsMaker-updater", "Accept": "application/vnd.github+json"}


def _get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r: return r.read()


def newer(a, b):
    num = lambda v: tuple(int(x) for x in v.split(".") if x.isdigit())
    return num(a) > num(b)


class Updater:
    def __init__(self, app_dir: Path, tmp: Path, report):
        self.app_dir, self.tmp, self.report, self.info = app_dir, tmp, report, None

    def check(self):
        """Чи є новіша версія. Мережа недоступна чи реліз дивний — просто без оновлення."""
        try:
            rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
            v = rel["tag_name"].lstrip("v")
            if not newer(v, VERSION): self.info = None; return
            assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
            meta = json.loads(_get(assets["release.json"])) if "release.json" in assets else {}
            setup = next((u for n, u in assets.items() if n.lower().endswith(".exe")), None)
            app_only = meta.get("runtime") == RUNTIME and "app.zip" in assets
            if not app_only and not setup: self.info = None; return
            self.info = dict(version=v, kind="app" if app_only else "full", url=assets["app.zip"] if app_only else setup)
        except Exception: self.info = None

    def _download(self, url, dst):
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=60) as r, open(dst, "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(256 * 1024):
                f.write(chunk); got += len(chunk)
                self.report("update", f"Завантажую версію {self.info['version']}", got / total if total else None)

    def apply(self):
        """'app' — файли програми вже замінено, треба перезапуститись; 'full' — шлях до завантаженого інсталятора."""
        if not self.info: raise RuntimeError("Оновлень немає")
        self.tmp.mkdir(parents=True, exist_ok=True)
        if self.info["kind"] == "full":
            dst = self.tmp / f"ShortsMaker-Setup-{self.info['version']}.exe"; self._download(self.info["url"], dst)
            return "full", dst
        z = Path(tempfile.mkdtemp(dir=self.tmp)) / "app.zip"; self._download(self.info["url"], z)
        with zipfile.ZipFile(z) as zf:
            names = set(zf.namelist())
            if "shorts.py" not in names: raise RuntimeError("Пошкоджене оновлення")
            for n in APP_FILES:                                      # спершу все розпакувати поруч, потім підмінити — без напівоновленої програми
                if n in names: (z.parent / n).write_bytes(zf.read(n))
        for n in APP_FILES:
            if (z.parent / n).is_file(): shutil.copyfile(z.parent / n, self.app_dir / n)
        shutil.rmtree(z.parent, ignore_errors=True)
        return "app", None
