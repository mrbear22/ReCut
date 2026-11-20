"""Оновлення з GitHub: що змінилось між нашим тегом і новим релізом."""
from datetime import datetime
from .core import HERE, PACKAGED, TMP, report
from .net import fetch

REPO, VERSION = "mrbear22/ReCut", "1.17.6"                     # репозиторій релізів; VERSION — тег релізу без «v»
RUNTIME_PATHS = ("build.sh", "installer.iss", "launcher/")           # змінилось це — потрібен новий інсталятор, інакше досить нових файлів з app/
UPDATE = {}

def github(path, raw=False):
    return fetch(f"https://raw.githubusercontent.com/{REPO}/{path}" if raw else f"https://api.github.com/repos/{REPO}/{path}", raw=raw)

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
        dst = TMP / f"ReCut-Setup-{u['version']}.exe"
        fetch(u["setup"], dst, lambda got, total: say(got / total if total else None))
        return dst
    new = {}
    for i, f in enumerate(u["files"]):                               # спершу все завантажити, потім підмінити — без напівоновленої програми
        if f["status"] != "removed": new[f["filename"][4:]] = github(f"{u['tag']}/{f['filename']}", raw=True)
        say((i + 1) / len(u["files"]))
    for f in u["files"]:
        for old in (f.get("previous_filename"), f["filename"] if f["status"] == "removed" else None):
            if old and old.startswith("app/"): (HERE / old[4:]).unlink(missing_ok=True)
    for name, data in new.items(): (HERE / name).parent.mkdir(parents=True, exist_ok=True); (HERE / name).write_bytes(data)
    return None
