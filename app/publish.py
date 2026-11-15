"""Публікація готових шортів: опис пише локальний ШІ (Ollama), відправка — через Buffer API.
Ключ Buffer лежить окремо від налаштувань (data/buffer.json) і в інтерфейс не віддається."""
import http.client, json, re, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path

BUFFER_API = "https://api.buffer.com"
# мова інструкції тягне мову відповіді: англійський промпт давав англійські назви до українського мовлення
CAPTION_PROMPT = """Ти пишеш підписи до вертикального короткого відео (TikTok / YouTube Shorts), вирізаного зі стріму.
Джерело: «{source}». Що відбувається в кліпі: {why}
Що кажуть у кліпі (розпізнане мовлення, може бути з помилками або порожнім):
{speech}

Пиши українською. Іншою мовою — лише якщо все мовлення явно іншою мовою.
Не вигадуй того, чого немає в мовленні чи описі. Без лапок і хештегів у назві.
Ніколи не пиши, що щось «невідомо» чи «незрозуміло»: якщо мовлення мало — зачепи емоцію чи інтригу моменту.
Відповідай лише JSON:
{{"title": "чіпка назва-гачок, до 70 символів",
  "description": "1-2 короткі речення, щоб додивились до кінця",
  "hashtags": ["3-6 доречних тегів без #, малими літерами"]}}"""
VIDEO_SERVICES = ("tiktok", "youtube", "instagram", "facebook", "threads", "twitter", "linkedin", "bluesky", "mastodon")   # куди Buffer публікує вертикальне відео
TEXT_MAX = {"twitter": 280, "bluesky": 300, "threads": 500, "mastodon": 500}   # більший допис Buffer відхилить
ALWAYS_TAGS = ["shorts"]                                           # YouTube надійніше впізнає шорт
TITLE_MAX, DESC_MAX, TAGS_MAX = 100, 2000, 8
YOUTUBE_CATEGORY = "20"                                            # «Ігри»: шорти зі стрімів
# Buffer бере відео лише за публічним посиланням і завантажує його в момент публікації (може бути за дні),
# тож файл має жити, поки пост не вийде. Анонімні файлообмінники або блокують Buffer (catbox, x0.at, pomf),
# або видаляють файл за години (uguu). Тому відео лежать у сховищі розробника: Cloudflare R2 за Worker (cloudflare/worker.js).
MEDIA_BASE = "https://shortsmaker-media.mykhailoholotiuk.workers.dev/"                                                    # адреса Worker, напр. https://shortsmaker-media.<акаунт>.workers.dev/
MEDIA_KEY = "b32da63b13f2f4263d6baf0f3ecb65fa"                    # такий самий у worker.js: не пароль, а захист від випадкових завантажень
MEDIA_MAX_MB, UPLOAD_CHUNK = 95, 256 * 1024                        # безкоштовний Worker не приймає понад 100 МБ


class Buffer:
    """Мінімальний клієнт GraphQL API Buffer на стандартній бібліотеці."""

    def __init__(self, key_file: Path):
        self.key_file, self._meta = key_file, None

    @property
    def key(self):
        try: return json.loads(self.key_file.read_text("utf-8")).get("key", "")
        except (OSError, ValueError): return ""

    def set_key(self, key):
        key = key.strip()
        self._meta = None                                           # інший акаунт — схему перечитаємо
        if not key: self.key_file.unlink(missing_ok=True); return
        if not re.fullmatch(r"[\x21-\x7e]{20,400}", key): raise ValueError("Це не схоже на ключ Buffer API")
        self.key_file.write_text(json.dumps({"key": key}), "utf-8")

    def gql(self, query, variables=None):
        if not self.key: raise RuntimeError("Buffer не підключено: встав ключ API")
        req = urllib.request.Request(BUFFER_API, json.dumps({"query": query, "variables": variables or {}}).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: out = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Buffer відповів {e.code}: {e.read()[:300].decode('utf-8', 'ignore')}") from e
        if out.get("errors"): raise RuntimeError("Buffer: " + "; ".join(e.get("message", "?") for e in out["errors"]))
        return out["data"]

    def channels(self):
        """Канали всіх організацій акаунта (TikTok, YouTube, …)."""
        orgs = self.gql("query { account { organizations { id name } } }")["account"]["organizations"]
        q = "query { channels(input: {organizationId: %s}) { id name displayName service avatar isQueuePaused } }"
        return [dict(c, org=o["name"], orgId=o["id"]) for o in orgs for c in self.gql(q % json.dumps(o["id"]))["channels"]]

    def scheduled(self):
        """Уже заплановані пости всіх організацій: щоб нові йшли в чергу після них."""
        orgs = self.gql("query { account { organizations { id } } }")["account"]["organizations"]
        q = """query { posts(input: {organizationId: %s, filter: {status: [scheduled]}, sort: [{field: dueAt, direction: asc}]}) {
                 edges { node { id text dueAt channelId } } } }"""
        return [e["node"] for o in orgs for e in self.gql(q % json.dumps(o["id"]))["posts"]["edges"]]

    def meta_schema(self):
        """Які поля YouTube/TikTok справді приймає createPost — з живої схеми (документація відстає).
        {"youtube": ("youtube", {"title", "privacy", …}), …}; порожньо — схема недоступна, беремо задокументовані назви."""
        if self._meta is not None: return self._meta
        self._meta = {}
        try:
            t = self.gql('query { __type(name: "PostInputMetaData") { inputFields { name type { name ofType { name } } } } }')["__type"] or {}
            for f in t.get("inputFields", []):
                kind, tn = f["name"].lower(), f["type"]["name"] or (f["type"]["ofType"] or {}).get("name")
                if kind in VIDEO_SERVICES and tn:
                    sub = self.gql('query($n: String!) { __type(name: $n) { inputFields { name } } }', {"n": tn})["__type"] or {}
                    self._meta[kind] = (f["name"], {x["name"] for x in sub.get("inputFields", [])})
        except RuntimeError: self._meta = {}
        return self._meta

    def post_metadata(self, service, title, privacy):
        """Назва й налаштування шорту для конкретної мережі — лише ті поля, що є в схемі."""
        want = {"youtube": dict(title=title, privacy=privacy, type="short", categoryId=YOUTUBE_CATEGORY, madeForKids=False, notifySubscribers=True),
                "tiktok": dict(title=title),
                "instagram": dict(type="reel", shouldShareToFeed=True),     # Instagram і Facebook без типу допису не приймають
                "facebook": dict(type="reel")}.get(service)
        if not want: return {}
        key, fields = self.meta_schema().get(service, (service, set(want)))
        body = {k: v for k, v in want.items() if k in fields and v not in ("", None)}
        return {key: body} if body else {}

    def create_post(self, channel, text, title, due_at, video_url, privacy):
        """Шорт на конкретний час. Назва — окремим полем для YouTube і TikTok."""
        meta = self.post_metadata(channel["service"], (title or text)[:TITLE_MAX], privacy)
        if (n := TEXT_MAX.get(channel["service"])) and len(text) > n: text = text[:n - 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-") + "…"   # X, Bluesky, Threads — короткі дописи
        inp = dict(channelId=channel["id"], text=text, schedulingType="automatic", mode="customScheduled", dueAt=due_at,
                   assets=[{"video": {"url": video_url}}], **({"metadata": meta} if meta else {}))
        q = """mutation($i: CreatePostInput!) { createPost(input: $i) {
                 ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }"""
        r = self.gql(q, {"i": inp})["createPost"]
        if "message" in r: raise RuntimeError(r["message"])
        return r["post"]

    def delete_post(self, post_id):
        """Прибрати пост із черги Buffer. Форму мутації беремо з живої схеми: документація відстає.
        Пост, якого вже немає (видалили на buffer.com чи вже вийшов), — теж успіх."""
        f = next((m for m in self.gql("query { __schema { mutationType { fields { name args { name type { kind name ofType { kind name } } } type { name ofType { name } } } } } }")
                  ["__schema"]["mutationType"]["fields"] if m["name"].lower() == "deletepost"), None)
        if not f: raise RuntimeError("Buffer API не вміє видаляти пости")
        tname = lambda t: t["name"] or (t.get("ofType") or {}).get("name")
        arg = f["args"][0]; aname, atype = arg["name"], tname(arg["type"])
        if arg["name"] == "input":                                 # deletePost(input: {id: …})
            fields = {x["name"] for x in (self.gql('query($n: String!) { __type(name: $n) { inputFields { name } } }', {"n": atype})["__type"] or {}).get("inputFields", [])}
            value = {next((k for k in ("id", "postId") if k in fields), "id"): post_id}
        else: value = post_id
        ret = self.gql('query($n: String!) { __type(name: $n) { possibleTypes { name fields { name } } } }', {"n": tname(f["type"])})["__type"] or {}
        errs = " ".join(f"... on {t['name']} {{ message }}" for t in ret.get("possibleTypes") or [] if any(x["name"] == "message" for x in t["fields"] or []))
        try: r = self.gql(f"mutation($v: {atype}!) {{ {f['name']}({aname}: $v) {{ __typename {errs} }} }}", {"v": value})[f["name"]] or {}
        except RuntimeError as e:
            if "not found" in str(e).lower(): return
            raise
        if r.get("message") and "not found" not in r["message"].lower(): raise RuntimeError(r["message"])

    def schema_summary(self):
        """Що вміє API насправді: мутації й поля вводу поста (документація відстає від схеми)."""
        q = """query { __schema { mutationType { fields { name args { name type { name kind ofType { name } } } } } }
                       post: __type(name: "CreatePostInput") { inputFields { name type { name kind ofType { name } } } }
                       meta: __type(name: "PostInputMetaData") { inputFields { name type { name ofType { name } } } }
                       video: __type(name: "VideoAssetInput") { inputFields { name type { name ofType { name } } } } }"""
        return self.gql(q)


def _ollama(url, model, prompt):
    body = dict(model=model, stream=False, format="json", options=dict(temperature=.7, num_ctx=4096),
                messages=[{"role": "user", "content": prompt}])
    with urllib.request.urlopen(urllib.request.Request(url + "chat", json.dumps(body).encode()), timeout=300) as r:
        return json.loads(json.load(r)["message"]["content"])


def clean_caption(raw):
    """Підрізати відповідь моделі до того, що приймуть TikTok і YouTube."""
    tags = raw.get("hashtags") or []
    tags = [re.sub(r"[^\w]", "", str(t).lstrip("#")).lower() for t in (tags if isinstance(tags, list) else str(tags).split())]
    tags = list(dict.fromkeys([*ALWAYS_TAGS, *(t for t in tags if t)]))[:TAGS_MAX]
    return dict(title=str(raw.get("title", "")).strip().strip('"«»')[:TITLE_MAX],
                description=str(raw.get("description", "")).strip()[:DESC_MAX], hashtags=tags)


def caption(source, why, speech, ollama_url, model):
    """Опис кліпу. Без Ollama — заготовка з назви джерела й того, що відбувається в кліпі."""
    if not model:
        return dict(clean_caption(dict(title=why or source, description="", hashtags=["shorts"])), ai=False)
    prompt = CAPTION_PROMPT.format(source=source, why=why or "невідомо", speech=speech[:6000] or "(мовлення немає)")
    return dict(clean_caption(_ollama(ollama_url, model, prompt)), ai=True, model=model)


def post_text(post):
    """Текст поста: опис і хештеги (назва для YouTube/TikTok іде окремим полем)."""
    tags = " ".join("#" + t for t in post.get("hashtags", []))
    return "\n\n".join(x for x in (post.get("description", "").strip(), tags) if x) or post.get("title", "")


class WorkerMedia:
    """Шорти для Buffer у сховищі розробника (Cloudflare R2 за Worker, код у cloudflare/worker.js).
    Користувачеві нічого налаштовувати: програма кладе файл, Buffer забирає його в момент публікації, потім файл прибираємо."""

    def __init__(self, base=MEDIA_BASE):
        self.base = base.rstrip("/") + "/" if base else ""

    def upload(self, path, name, progress=lambda frac: None):
        path = Path(path); size = path.stat().st_size
        if not self.base: raise RuntimeError("Сховище відео для Buffer ще не налаштоване в цій версії програми")
        if size > MEDIA_MAX_MB * 2 ** 20: raise RuntimeError(f"Шорт більший за {MEDIA_MAX_MB} МБ — сховище не прийме")
        u = urllib.parse.urlsplit(self.base + "v/" + name); c = http.client.HTTPSConnection(u.netloc, timeout=120)
        try:
            c.putrequest("PUT", u.path)
            for k, v in {"Content-Type": "video/mp4", "Content-Length": size, "X-Upload-Key": MEDIA_KEY, "User-Agent": "ShortsMaker"}.items(): c.putheader(k, str(v))
            c.endheaders(); sent = 0
            with path.open("rb") as fh:                              # частинами: великий файл не в пам'яті й видно поступ
                while chunk := fh.read(UPLOAD_CHUNK):
                    c.send(chunk); sent += len(chunk); progress(sent / size)
            r = c.getresponse(); body = r.read().decode("utf-8", "ignore").strip()
        except OSError as e: raise RuntimeError(f"Не вдалося викласти відео: {e}") from e
        finally: c.close()
        if r.status != 201: raise RuntimeError(f"Сховище відео відповіло {r.status}: {body[:150]}")
        return self.base + "v/" + name

    def delete(self, url):
        """Прибрати відео, яке Buffer уже опублікував. Не вийшло — не біда: сховище саме чистить усе старше 45 днів."""
        if not self.base or not url.startswith(self.base): return
        try: urllib.request.urlopen(urllib.request.Request(url, method="DELETE", headers={"X-Upload-Key": MEDIA_KEY, "User-Agent": "ShortsMaker"}), timeout=30).close()
        except OSError: pass
