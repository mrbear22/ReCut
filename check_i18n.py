"""Які українські тексти інтерфейсу ще без перекладу: python check_i18n.py [мова, типово en].
Шукає рядки з кирилицею в коді сторінки (app/js, app/*.js, app/ui.html) і в повідомленнях сервера (raise …Error, report),
і перевіряє їх так само, як рушій app/i18n.js: точний збіг, шаблон з {} або той самий текст з малої літери.
Вставки `${…}` у шаблонних рядках рахуються як {}. Те, що в коді складається з шматків, перевіряйте очима — скрипт підказує, а не судить."""
import json, re, sys
from pathlib import Path

APP = Path(__file__).parent / "app"
CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
norm = lambda s: re.sub(r"\s+", " ", s).strip()
CODE = re.compile(r"=>|\$\{|['\]\[]|\.map\(|\?\s*$")             # вкладений шаблон розібрався криво — це шматок коду, а не текст
KEEP = {"УКР"}                                                     # назва мови на перемикачі — не перекладається

def dictionary(lang):
    src = (APP / "lang" / f"{lang}.js").read_text("utf-8")
    body = src[src.index("{", src.index(f"LANGS.{lang}")):src.rindex("}") + 1]
    return json.loads(re.sub(r",\s*}$", "}", body))

def matcher(d):
    exact, pats = {}, []
    for k, v in d.items():
        k = norm(k)
        if "{}" not in k: exact[k] = exact[k.strip(" ·:—-|")] = v; continue
        pats.append(re.compile("^" + "(.+?)".join(map(re.escape, k.split("{}"))) + "$", re.S))
        for part in k.split("{}"):                                  # шматки шаблону між тегами — теж переклад
            if CYR.search(part.strip()): exact.setdefault(norm(part), "")
    def fits(s):                                                  # шаблон підходить, і вставки в ньому теж перекладаються (як у рушії)
        return any((m := p.match(s)) and all(ok(g) for g in m.groups() if g != "1") for p in pats)
    def ok(s, glued=False):
        s = norm(s)
        if not CYR.search(s) or s in exact or fits(s.replace("{}", "1")): return True
        if s and s[0] != s[0].upper() and s[0].upper() + s[1:] in exact: return True
        return glued and fits(s + ": 1")                           # '…: ' + помилка — склеюється вже в коді
    return ok

def strings(path):
    """(рядок файлу, текст) з кирилицею: JS/HTML — літерали й текст між тегами; Python — лише те, що бачить користувач."""
    text = path.read_text("utf-8")
    if path.suffix == ".py":
        for m in re.finditer(r"(?:Error|report)\((?:[^()\"']*,\s*)?f?\"([^\"]*)\"", text):
            yield text.count("\n", 0, m.start()) + 1, re.sub(r"\{[^}]*\}", "{}", m.group(1))
        return
    code = re.sub(r"(?m)(^|\s)//\s.*$", r"\1", text)               # коментарі — не інтерфейс
    for m in re.finditer(r"'((?:\\.|[^'\\\n])*)'|\"((?:\\.|[^\"\\\n])*)\"|`((?:\\.|[^`\\])*)`", code):
        s = re.sub(r"\\(['\"`])", r"\1", next(g for g in m.groups() if g is not None))
        if m.group(3) is not None: s = re.sub(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "{}", s)
        for piece in re.split(r"<[^>]+>", s):                      # HTML у рядку: кожен шматок тексту перекладається окремо
            if CYR.search(piece) and not CODE.search(piece): yield code.count("\n", 0, m.start()) + 1, piece
    for m in re.finditer(r"\$\{[^`'{}\n]*'([^'\n<>=]*[А-Яа-яІіЇїЄєҐґ][^'\n<>=]*)'", code):   # рядки всередині ${…} вкладених шаблонів
        yield code.count("\n", 0, m.start()) + 1, m.group(1)
    if path.suffix == ".html":
        for m in re.finditer(r">([^<>]+)<", text):
            if CYR.search(m.group(1)): yield text.count("\n", 0, m.start()) + 1, m.group(1)

def main(lang="en"):
    ok, missing = matcher(dictionary(lang)), {}
    files = [*sorted((APP / "js").glob("*.js")), APP / "publish.js", APP / "ui.html", *sorted((APP / "recut").glob("*.py"))]
    for f in files:
        for line, raw in strings(f):
            s = norm(raw.strip(" ·:—-|"))
            if s and s not in KEEP and not ok(s, raw.rstrip().endswith(":")): missing.setdefault(s, f"{f.relative_to(APP.parent)}:{line}")
    for s, where in missing.items(): print(f"{where}\t{s}")
    print(f"\nБез перекладу ({lang}): {len(missing)}", file=sys.stderr)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
    main(*sys.argv[1:])
