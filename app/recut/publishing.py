"""Публікація через Buffer: черга, сховище відео."""
import os, time, uuid
from datetime import datetime
from . import buffer
from .core import DATA, report
from .projects import load_project, projects, update_project

BUFFER = buffer.Buffer(DATA / "buffer.json")
MEDIA = buffer.WorkerMedia()

def render_files(p, path):
    """Записи готового шорту в історії рендерів проєкту (той самий файл міг рендеритись кілька разів)."""
    return [f for r in p["renders"] for f in r["files"] if f["path"] == path]


def save_post(pid, path, post):
    def put(p):
        for f in render_files(p, path): f["post"] = {**f.get("post", {}), **post}
    update_project(pid, put)

def unqueue(pid, path):
    """Повернути шорт до редагування: прибрати його пости з черги Buffer і забути статус (посилання на відео лишається)."""
    f = next(iter(render_files(load_project(pid), path)), None)
    if not f: raise ValueError("Шорт не знайдено в проєкті")
    left = {}
    for cid, rec in f.get("post", {}).get("buffer", {}).items():
        if not rec.get("id"): continue
        try: BUFFER.delete_post(rec["id"])
        except Exception as e: left[cid] = rec; err = str(e)[:200]
    save_post(pid, path, {"buffer": left})
    if left: raise RuntimeError(err)
    return {}

def publish_batch(pid, plan, privacy, limit=0):
    """Кожен шорт — у свої канали (вибрані на картці) на свій час; результат пишемо в проєкт, щоб бачити статус.
    limit — скільки постів тариф Buffer тримає в черзі каналу (0 — без межі): що не влазить, у сховище навіть не викладаємо."""
    chans = {c["id"]: c for c in BUFFER.channels()}; p = load_project(pid); ok, errors = 0, []; t0 = time.time()
    room = {}
    if limit:
        for q in BUFFER.scheduled(): room[q["channelId"]] = room.get(q["channelId"], 0) + 1
        room = {cid: int(limit) - room.get(cid, 0) for cid in chans}
    for i, item in enumerate(plan):
        n = f" {i + 1} з {len(plan)}" if len(plan) > 1 else ""
        say = lambda frac, i=i, n=n: report("upload", f"Викладаю відео{n}", (i + frac) / len(plan), t0)
        say(0)
        if limit:
            item["channels"] = [cid for cid in item.get("channels", []) if room.get(cid, 0) > 0]
            if not item["channels"]: errors.append(f"черга Buffer повна ({limit} постів на канал)"); continue
            for cid in item["channels"]: room[cid] -= 1
        f = next(iter(render_files(p, item["path"])), None)
        if not f: errors.append("файл не знайдено"); continue
        post, sent = f.get("post", {}), {}
        try: url = media_url(pid, f, say)
        except Exception as e: errors.append(str(e)[:200]); save_post(pid, f["path"], {"buffer": {**post.get("buffer", {}), "_media": dict(error=str(e)[:200])}}); continue
        for cid in item.get("channels", []):
            try: r = BUFFER.create_post(chans[cid], buffer.post_text(post), post.get("title", ""), item["dueAt"], url, privacy); sent[cid] = dict(id=r["id"], dueAt=item["dueAt"]); ok += 1
            except Exception as e: sent[cid] = dict(error=str(e)[:200]); errors.append(str(e)[:200])
        save_post(pid, f["path"], {"buffer": {k: v for k, v in {**post.get("buffer", {}), **sent}.items() if k != "_media"}})
    report("", "")
    return dict(ok=ok, errors=len(errors), first_error=errors[0] if errors else "")

MEDIA_GRACE_S, MEDIA_CHECK_S = 15 * 60, 10 * 60                   # Buffer забирає відео в момент публікації — чверть години запасу на це

def cleanup_media():
    """Прибрати зі сховища відео, які Buffer уже опублікував: жоден їхній пост не чекає в черзі, і час вийшов."""
    if not BUFFER.key: return
    try: waiting = {q["id"] for q in BUFFER.scheduled()}
    except Exception: return                                        # Buffer недоступний — перевіримо наступного разу
    gone = lambda x: x["id"] not in waiting and datetime.fromisoformat(x["dueAt"].replace("Z", "+00:00")).timestamp() < time.time() - MEDIA_GRACE_S
    for p in projects():
        for r in p["renders"]:
            for f in r["files"]:
                post = f.get("post", {}); u = post.get("mediaUrl", "")
                sent = [x for x in post.get("buffer", {}).values() if x.get("id")]
                if u and sent and all(map(gone, sent)) and MEDIA.delete(u): save_post(p["id"], f["path"], {"mediaUrl": "", "mediaStamp": ""})

def media_janitor():
    """Поки програма відкрита — раз на 10 хвилин прибирати опубліковане."""
    while True:
        try: cleanup_media()
        except Exception as e: print("cleanup_media:", e)
        time.sleep(MEDIA_CHECK_S)

def media_url(pid, f, progress=lambda frac: None):
    """Публічне посилання на файл шорту: викладаємо один раз, далі беремо збережене (поки файл той самий і лежить у нашому сховищі)."""
    post, stamp = f.get("post", {}), f"{os.path.getsize(f['path'])}:{os.path.getmtime(f['path'])}"
    if post.get("mediaUrl", "").startswith(MEDIA.base) and post.get("mediaStamp") == stamp: return post["mediaUrl"]
    name = uuid.uuid5(uuid.NAMESPACE_URL, f["path"] + stamp).hex[:24] + ".mp4"
    url = MEDIA.upload(f["path"], name, progress)
    save_post(pid, f["path"], {"mediaUrl": url, "mediaStamp": stamp}); f.setdefault("post", {}).update(mediaUrl=url, mediaStamp=stamp)
    return url
