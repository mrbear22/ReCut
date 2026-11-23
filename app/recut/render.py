"""Рендер шортів: фільтри ffmpeg, субтитри ASS, музика, хуки й петлі."""
import json, os, re, shutil, tempfile, threading, time, uuid
from pathlib import Path
from .art import ART, art, frame, layer
from .core import Cancelled, CANVAS, ev, HttpError, learn, on, PAD, RENDERS, report, run, TASK, THUMBS
from .fonts import pick_font
from .media import amix, encode, ffbin, pick_encoder, probe
from .projects import load_project, update_project
from .twitch import local_input

# ── рендер ──
JOB = dict(running=False, n=0, err="", out="", id="", project="", task="", cancelled=False)   # один рендер за раз; стан — для інтерфейсу
def kept(a, b, cuts):
    """Інтервали джерела, що лишаються в кліпі [a, b] після вирізання пропусків."""
    out, t = [], a
    for x, y in sorted(cuts) + [(b, b)]:
        if min(x, b) - t > 0.05: out.append((t, min(x, b)))
        t = max(t, y)
    return out

ass_col = lambda c: f"&H00{c[5:7]}{c[3:5]}{c[1:3]}&".upper()     # #rrggbb -> ASS &H00BBGGRR&

def cue_owner(c, subs_all):
    """Елемент «Субтитри», якому належить репліка (кожен спікер — свій елемент); без позначки — першому."""
    return next((e for e in subs_all if e["id"] == c.get("sid")), subs_all[0] if subs_all else None)

SUB_STYLE = ("font", "size", "color", "hl", "karaoke", "upper", "outline", "stroke", "anim", "x", "y", "w")   # що репліка може мати своє

def cue_style(c, el):
    """Стиль репліки: свій, якщо її від'єднали від глобального стилю доріжки, інакше — доріжки."""
    own = c.get("own") or {}
    return dict(el, **{k: own[k] for k in SUB_STYLE if k in own})

def word_tags(f, size):
    """Пословне форматування репліки: (теги перед словом, повернення до стилю після нього)."""
    pre, post = "", ""
    if "b" in f: pre += f"\\b{1 if f['b'] else 0}"; post += "\\b1"   # субтитри типово жирні
    if f.get("i"): pre += "\\i1"; post += "\\i0"
    if f.get("u"): pre += "\\u1"; post += "\\u0"
    if f.get("s") and float(f["s"]) != 1: pre += f"\\fs{size * float(f['s']):.0f}"; post += f"\\fs{size:.0f}"
    return pre, post

ass_time = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
ASS_INTRO = {"pop": r"\fscx80\fscy80\t(0,90,\fscx100\fscy100)", "fade": r"\fad(150,0)"}   # поява фрази

class AssStyles:
    """Стилі ASS: однаковий вигляд (шрифт, розмір, колір, обведення, місце) — один стиль."""
    def __init__(self, width): self.width, self.names, self.lines = width, {}, []

    def name(self, st):
        size, x, w, base, bord = float(st.get("size", 84)), float(st["x"]), float(st.get("w", 900)), ass_col(st.get("color", "#ffffff")), float(st.get("outline", 6))
        line = ass_col(st.get("stroke") or "#000000")
        key = json.dumps([st.get("font"), round(size), base, line, bord, round(x), round(w)])
        if key not in self.names:
            self.names[key] = f"S{len(self.names)}"
            self.lines.append(f"Style: {self.names[key]},{pick_font(st.get('font'))[0].replace(',', ' ')},{size:.0f},{base},{base},{line},&H64000000,-1,0,0,0,100,100,0,0,1,"
                              f"{bord:.1f},{size * 0.04:.1f},5,{max(0, x):.0f},{max(0, self.width - x - w):.0f},0,1")
        return self.names[key]

def word_markup(t, f, lit, size, hl, base):
    """Слово з пословним форматуванням; lit — це слово зараз звучить (караоке)."""
    col = hl if lit else ass_col(f["c"]) if re.fullmatch(r"#[0-9a-fA-F]{6}", f.get("c") or "") else base
    pre, post = word_tags(f, size)
    if col != base: pre, post = f"\\1c{col}" + pre, f"\\1c{base}" + post
    return f"{{{pre}}}{t}{{{post}}}" if pre else t

def cue_lines(c, st, style, keep):
    """Рядки Dialogue репліки: з караоке — по рядку на слово, що звучить; через вирізаний пропуск — шматками; час — уже без пропусків."""
    raw = c["text"].split()
    if not raw: return []
    size = float(st.get("size", 84)); x, y, w = float(st["x"]), float(st["y"]), float(st.get("w", 900))
    hl, base, intro = ass_col(st.get("hl", "#ffcc33")), ass_col(st.get("color", "#ffffff")), ASS_INTRO.get(st.get("anim", "pop"), "")
    fmt = c.get("fmt") if len(c.get("fmt") or []) == len(raw) else [None] * len(raw)
    words = [re.sub(r"[{}\\]", "", t.upper() if st.get("upper") else t) for t in raw]
    k = c.get("k") if len(c.get("k") or []) == len(words) else [c["a"] + i * (c["b"] - c["a"]) / len(words) for i in range(len(words))]
    spans = list(zip(k, k[1:] + [c["b"]], range(len(words)))) if st.get("karaoke", True) else [(c["a"], c["b"], -1)]
    out, first = [], True
    for s0_, e_, i in spans:
        body = " ".join(word_markup(t, fmt[j] or {}, j == i, size, hl, base) for j, t in enumerate(words)); off = 0.0
        for s0, s1 in keep:
            a, b = max(s0_, s0) - s0 + off, min(e_, s1) - s0 + off; off += s1 - s0
            if b - a < 0.02: continue
            out.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{{\\an5\\pos({x + w / 2:.0f},{y + size * 0.7:.0f}){intro * first}}}{body}"); first = False
    return out

def ass_document(W, H, styles, lines):
    return (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) + "\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + "\n".join(lines) + "\n")

def subs_ass(cues, keep, subs_all, canvas):
    """ASS кліпу: кожен увімкнений елемент «Субтитри» — свій стиль і місце, зі своїми репліками; репліка може мати свій стиль
    і пословне форматування; час — уже без вирізаних пропусків."""
    W, H = canvas; styles, lines = AssStyles(W), []
    for c in cues:
        el = cue_owner(c, subs_all)
        if not el or not on(el): continue
        st = cue_style(c, el); lines += cue_lines(c, st, styles.name(st), keep)
    return ass_document(W, H, styles.lines, lines)

def spans(e, net):
    """Частини показу елемента в кліпі: [(з, до)], секунди від початку вже без пропусків; «до» 0 — до кінця кліпу."""
    return [(float(a or 0), float(b or 0) or net) for a, b in e.get("segs") or [(e.get("from"), e.get("to"))]]

def when(e):
    """Час показу елемента в кліпі: з/до, секунди від початку вже без пропусків."""
    segs = [(float(a or 0), float(b or 0)) for a, b in e.get("segs") or [(e.get("from"), e.get("to"))]]
    if segs == [(0, 0)]: return ""
    return ":enable='" + "+".join(f"between(t,{a},{b or 1e9})" for a, b in segs) + "'"

OWN_KEEP = ("id", "type", "on", "solo", "from", "to", "segs")      # це в кліпі завжди спільне, навіть у не глобального елемента

def clip_elements(elements, c):
    """Елементи для кліпу: свої частини показу (segs) замість спільних з/до; сховані в кліпі й ті, яких у кліп не додали, — геть.
    Не глобальний у цьому кліпі елемент (c["own"]) має свої налаштування замість спільних."""
    own, mine, out = c.get("segs") or {}, c.get("own") or {}, []
    for e in elements:
        if e["id"] in mine: e = dict(e, **{k: v for k, v in mine[e["id"]].items() if k not in OWN_KEEP and not k.startswith("_")})
        segs = own.get(e["id"])
        if segs is None:
            if not e.get("solo"): out.append(e)
        elif segs: out.append(dict(e, segs=segs, **{"from": segs[0][0], "to": segs[-1][1]}))   # анімація — на першому вході й останньому виході
    return out

def overlay_art(e, i, size, last, nxt):
    """Елемент-картинка (вхід i) з анімацією входу."""
    st, en, anim = float(e.get("from") or 0), float(e.get("to") or 0), e.get("anim", "none")
    x, y, pre = f"{int(e['x']) - PAD}", f"{int(e['y']) - PAD}", []
    if anim != "none": pre += ["format=rgba", f"fade=t=in:st={st}:d=0.3:alpha=1"] + [f"fade=t=out:st={max(st, en - 0.3)}:d=0.3:alpha=1"] * (en > 0)
    if anim == "pop":
        k = f"(0.6+0.4*clip((t-{st})/0.25\\,0\\,1))"
        pre.append(f"scale=w='iw*{k}':h='ih*{k}':eval=frame"); x, y = f"'{x}+({size[0]}-w)/2'", f"'{y}+({size[1]}-h)/2'"
    if anim == "slide": y = f"'{y}+140*(1-clip((t-{st})/0.35,0,1))'"
    f = [f"[{i}:v]{','.join(pre)}[a{i}]"] if pre else []
    return f + [f"[{last}][{f'a{i}' if pre else f'{i}:v'}]overlay={x}:{y}:shortest=1{when(e)}[{nxt}]"]

def bar_filter(e, k, last, out, total, W, enable=""):
    """Прогрес-бар: смуга росте від 0 до повної ширини за total с."""
    return [f"color=c={e.get('color', '#ffcc33')}:s={W}x{ev(float(e.get('h', 12)))}:r=30[pg{k}]",
            f"[{last}][pg{k}]overlay=x='-w+w*t/{total:.3f}':y={int(e['y'])}:shortest=1{enable}[{out}]"]

def join_kept(n, audio, na):
    """Пропуски вирізано: кожен збережений шматок — свій вхід ffmpeg (0…n-1), тож вирізане не декодується й не качається; склеєні в [cv] ([ca])."""
    f = ["".join(f"[{i}:a:{k}]" for k in range(na)) + f"amix=inputs={na}:normalize=0[ka{i}]" for i in range(n)] if audio and na > 1 else []   # звучать усі доріжки
    a = lambda i: f"[ka{i}]" if na > 1 else f"[{i}:a]"
    return f + ["".join(f"[{i}:v]" + (a(i) if audio else "") for i in range(n)) + f"concat=n={n}:v=1:a={int(audio)}[cv]" + "[ca]" * audio]

def background(bg, W, H):
    """Фон [bg] з [bg0]: колір або розмите й затемнене відео (блюр у 1/4 роздільності — швидко)."""
    if bg.get("style") == "color": return f"[bg0]scale={W}:{H},drawbox=color={bg['color']}:t=fill[bg]"
    return (f"[bg0]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
            f"gblur=sigma={float(bg.get('blur', 5)):g},eq=brightness={-float(bg.get('dim', 0.12)):g},scale={W}:{H}[bg]")

# ── ефект: діє на все під ним у списку елементів ──
def zoom_of(c, r, f):
    """Призум: рамка f на кадрі джерела — те, що має показати шар r; інший шар під ефектом (кадр c) наближається так само."""
    (x, y, w, h), (rx, ry, rw, rh), (fx, fy, fw, fh) = c, r, f; nw, nh = w * fw / rw, h * fh / rh
    return [min(max(fx + (x - rx) * fw / rw, 0), max(0, 1 - nw)), min(max(fy + (y - ry) * fh / rh, 0), max(0, 1 - nh)), nw, nh]

def zooms(e, els, net):
    """Призуми над шаром e: [(кадр під час ефекту, плавно, частини показу)] — найближчий до шару першим."""
    out, i = [], els.index(e)
    for j, f in enumerate(els[i + 1:], i + 1):
        if f["type"] != "fx" or f.get("kind") != "zoom" or not f.get("src"): continue
        r = next((g for g in reversed(els[:j]) if g["type"] in ("video", "cam")), None)
        if r: out.append((zoom_of(e["src"], r["src"], f["src"]), f.get("ease") == "smooth", spans(f, net)))
    return out

def window(k, c, zs):
    """Вираз ffmpeg для k-ї величини кадру (x, y, w, h) у час t: звичайний кадр, а в частинах призуму — кадр ефекту (плавно — наїздом)."""
    expr = f"{c[k]:.6f}"
    for z, smooth, segs in reversed(zs):
        for a, b in segs:
            p = f"clip((t-{a:.3f})/{max(.01, b - a):.3f},0,1)"
            v = f"({c[k]:.6f}+({z[k]:.6f}-{c[k]:.6f})*{p}*{p}*(3-2*{p}))" if smooth else f"{z[k]:.6f}"
            expr = f"if(between(t,{a:.3f},{b:.3f}),{v},{expr})"
    return expr

def zoom_crop(e, zs, sw, sh, dw, dh):
    """Кадр, що змінюється з часом: crop розміру не міняє, тож — сталий шматок U з усіма кадрами, масштаб покадрово й crop на місце."""
    boxes = [e["src"]] + [z for z, _, _ in zs]
    ux, uy = int(min(b[0] for b in boxes) * sw), int(min(b[1] for b in boxes) * sh)
    uw, uh = min(sw - ux, ev(max(b[0] + b[2] for b in boxes) * sw - ux + 1)), min(sh - uy, ev(max(b[1] + b[3] for b in boxes) * sh - uy + 1))
    s = f"({dw}/({window(2, e['src'], zs)}*{sw}))"
    return (f"crop={uw}:{uh}:{ux}:{uy},scale=w='max({dw},trunc({uw}*{s}/2)*2)':h='max({dh},trunc({uh}*{s}/2)*2)':eval=frame,"
            f"crop={dw}:{dh}:x='({window(0, e['src'], zs)}*{sw}-{ux})*{s}':y='({window(1, e['src'], zs)}*{sh}-{uy})*{s}',setsar=1")

def fx_filter(e, n, last, W, H, net):
    """Ефект на все, що вже складено під ним ([last]): (фільтри, нова мітка). Призум — не тут, а в кадрі шарів відео."""
    en, kind, out = when(e), e.get("kind"), f"x{n}"
    if kind == "bw": return [f"[{last}]hue=s=0{en}[{out}]"], out
    if kind == "blur": return [f"[{last}]gblur=sigma={float(e.get('blur', 12)):g}{en}[{out}]"], out
    if kind == "fried": return [f"[{last}]eq=contrast=1.8:saturation=2.6{en},unsharp=5:5:1.2{en}[{out}]"], out
    if kind == "shake":
        a = float(e.get("amp", 14)); g = ev(W + 4 * a), ev(H + 4 * a)
        return [f"[{last}]split[sa{n}][sb{n}]", f"[sb{n}]scale={g[0]}:{g[1]},crop={W}:{H}:x='(iw-ow)/2+{a:g}*sin(t*47)':y='(ih-oh)/2+{a:g}*cos(t*37)'[sc{n}]",
                f"[sa{n}][sc{n}]overlay=0:0:shortest=1{en}[{out}]"], out
    if kind == "flash":
        f, cur = [], last
        for j, (a, _) in enumerate(spans(e, net)):
            f += [f"color=c=white:s={W}x{H}:r=30,format=rgba,fade=t=out:st={a:.3f}:d=0.35:alpha=1[fw{n}_{j}]",
                  f"[{cur}][fw{n}_{j}]overlay=0:0:shortest=1:enable='between(t,{a:.3f},{a + .35:.3f})'[fo{n}_{j}]"]; cur = f"fo{n}_{j}"
        return f, cur
    return [], last

def video_layer(e, n, i, inp, sw, sh, last, zs=()):
    """Шар відео чи вебки поверх [last]: кадрування (з призумами над ним), маска форми, рамка. Повертає (фільтри, нова мітка)."""
    c, dw, dh = layer(e, sw, sh); x, y = int(e["x"]), int(e["y"])
    if zs: c = zoom_crop(e, zs, sw, sh, dw, dh)
    f = [f"[s{i}]{c},format=rgba[c{n}]", f"[c{n}][{inp[e['id'], 'mask']}:v]alphamerge[e{n}]"] if (e["id"], "mask") in inp else [f"[s{i}]{c}[e{n}]"]
    f.append(f"[{last}][e{n}]overlay={x}:{y}:shortest=1{when(e)}[l{n}]")   # маска-картинка довша за склеєне відео — кліп не подовжується
    if (e["id"], "ring") not in inp: return f, f"l{n}"
    b = round(float(e["bw"])); f.append(f"[l{n}][{inp[e['id'], 'ring']}:v]overlay={x - b}:{y - b}:shortest=1{when(e)}[r{n}]")
    return f, f"r{n}"

def build_filter(sw, sh, elements, keep, na, inp, sizes, subs, canvas):
    """na: скільки звукових доріжок; inp: (id елемента, роль) -> номер входу ffmpeg; sizes: id -> розмір картинки елемента."""
    els = [e for e in elements if on(e) and e["type"] not in ("subs", "bg", "music")]; vids = [e for e in els if e["type"] in ("video", "cam")]
    bg = next((e for e in elements if e["type"] == "bg" and on(e)), {}); net = sum(e - s for s, e in keep); W, H = canvas
    f, src = [], "0:v"
    if len(keep) > 1: f += join_kept(len(keep), int(na > 0), na); src = "cv"
    elif na > 1: f.append(amix(na, "am"))                               # звучать усі доріжки
    f += [f"[{src}]split={1 + len(vids)}[bg0]" + "".join(f"[s{i}]" for i in range(len(vids))), background(bg, W, H)]
    last = "bg"
    for n, e in enumerate(els, 1):
        if e["type"] in ART: f += overlay_art(e, inp[e["id"], "art"], sizes[e["id"]], last, f"l{n}"); last = f"l{n}"
        elif e["type"] == "progress": f += bar_filter(e, n, last, f"l{n}", net, W, when(e)); last = f"l{n}"   # смуга росте від 0 до повної ширини за кліп
        elif e["type"] == "fx": fx_f, last = fx_filter(e, n, last, W, H, net); f += fx_f
        else: layer_f, last = video_layer(e, n, vids.index(e), inp, sw, sh, last, zooms(e, els, net)); f += layer_f
    f.append(f"[{last}]{'ass=subs.ass:fontsdir=.' if subs else 'null'}[v]")    # ffmpeg працює в теці з subs.ass і шрифтом
    return ";".join(f)

def rearrange(dst, parts, bars, args, audio, W, tick):
    """Переставити шматки готового кліпу: хук (смішний момент) — на самий початок, петля — шорт з мітки до кінця, далі початок до мітки,
    тож коли відео повторюється, стику не видно. parts — [(з, до)] у часі готового файлу.
    bars — прогрес-бари: їх малюємо тут, щоб смуга росла від нового початку."""
    n, total = len(parts), sum(e - s for s, e in parts)
    f = [f"[0:v]split={n}" + "".join(f"[sv{i}]" for i in range(n))] + ([f"[0:a]asplit={n}" + "".join(f"[sa{i}]" for i in range(n))] if audio else [])
    for i, (s, e) in enumerate(parts):
        f.append(f"[sv{i}]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        if audio: f.append(f"[sa{i}]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    f.append("".join(f"[v{i}]" + f"[a{i}]" * audio for i in range(n)) + f"concat=n={n}:v=1:a={int(audio)}[c0]" + "[a]" * audio); last = "c0"
    for k, e in enumerate(bars, 1):
        f += bar_filter(e, k, last, f"c{k}", total, W); last = f"c{k}"
    tmp = dst.with_name(dst.stem + ".parts.mp4")
    try: encode(["-i", str(dst), "-filter_complex", ";".join(f), "-map", f"[{last}]", *(["-map", "[a]"] if audio else []),
                 *args, *(["-c:a", "aac", "-b:a", "192k"] if audio else []), "-movflags", "+faststart", str(tmp)], total, tick)
    except BaseException as e:                                     # збій чи скасування — недороблений файл геть
        tmp.unlink(missing_ok=True)
        if isinstance(e, RuntimeError): raise RuntimeError(f"Хук і петля: {e}") from e
        raise
    os.replace(tmp, dst)
    return total

def clip_parts(c, keep, net):
    """Порядок шматків готового кліпу (час файлу): хук на початок, далі петля або кліп як є. None — переставляти нічого."""
    inside = lambda t: any(s < t < e for s, e in keep)
    loop = out_pos(float(c["loop"]), keep) if c.get("loop") is not None and inside(float(c["loop"])) else 0
    if not .5 < loop < net - .5: loop = 0
    hook = [out_pos(float(t), keep) for t in c["hook"]] if len(c.get("hook") or []) == 2 else None
    if hook and hook[1] - hook[0] < .3: hook = None
    if not loop and not hook: return None
    return ([tuple(hook)] if hook else []) + ([(loop, net), (0, loop)] if loop else [(0, net)])

def out_pos(x, keep):
    """Час у готовому кліпі для моменту x джерела (вирізані пропуски не рахуються)."""
    return sum(min(x, e) - s for s, e in keep if x > s)

def music_parts(els, net):
    """Шматки музики кліпу: (файл, з якої секунди файлу, де в кліпі, скільки, гучність, наростання, згасання).
    Момент треку = зсув треку + час у кліпі, тож розрізані шматки грають у такт, ніби трек не переривався."""
    out = []
    for e in els:
        if e["type"] != "music" or not on(e) or not Path(e.get("path", "")).is_file(): continue
        off, dur, vol = float(e.get("off") or 0), float(e.get("dur") or 1e9), float(e.get("vol", 1))
        segs = [(float(a or 0), float(b or 0) or net) for a, b in e.get("segs") or [(e.get("from"), e.get("to"))]]
        for k, (a, b) in enumerate(segs):
            a, b = max(a, -off, 0), min(b, net, dur - off)
            if b - a < .05: continue
            fin = float(e.get("fin") or 0) if k == 0 else .02                       # усередині — лише проти клацання
            fout = max(float(e.get("fout") or 0) if k == len(segs) - 1 else 0, .03)
            out.append((e["path"], off + a, a, b - a, vol, min(fin, (b - a) / 2), min(fout, (b - a) / 2)))
    return out

def audio_filter(main, parts, first_input, video_vol, net):
    """Звук кліпу: звук відео з потрібною гучністю + шматки музики з фейдами. Повертає (фільтри, мітка виходу)."""
    f, mix = [], []
    if main: f.append(f"[{main}]volume={video_vol:.3f}[av]"); mix.append("[av]")
    for k, (_, _, at, length, vol, fin, fout) in enumerate(parts):
        fx = [f"atrim=0:{length:.3f}", "asetpts=PTS-STARTPTS", f"volume={vol:.3f}"]
        if fin: fx.append(f"afade=t=in:st=0:d={fin:.3f}")
        if fout: fx.append(f"afade=t=out:st={length - fout:.3f}:d={fout:.3f}")
        fx.append(f"adelay={round(at * 1000)}:all=1")
        f.append(f"[{first_input + k}:a]" + ",".join(fx) + f"[mu{k}]"); mix.append(f"[mu{k}]")
    if not mix: return f, None
    f.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=longest,atrim=0:{net:.3f}[aout]")   # мікс не довший за кліп
    return f, "aout"

def out_name(pr):
    return re.sub(r'[<>:"/\\|?*]+', " ", pr["name"] or Path(pr["video"]).stem).strip(" .") or "shorts"

def render_dir(pr):
    """Тека для діалогу рендеру: куди рендерили востаннє, інакше renders/<проєкт> (або renders, поки її немає)."""
    last = next((r["out"] for r in pr["renders"] if Path(r["out"]).is_dir()), None)
    return last or str(RENDERS / out_name(pr) if (RENDERS / out_name(pr)).is_dir() else RENDERS)

RENDERED = ("video", "cam", "subs", "bg", "music", "progress", "fx")     # не картинки, але рендеряться; старих типів, яких більше немає, — ні
OWN_LOOK = ("x", "y", "from", "to", "segs", "anim", "on", "id")      # не впливає на вигляд картинки елемента

def clip_work(c):
    """Скільки секунд відео закодувати: з хуком чи петлею кліп кодується двічі."""
    keep = kept(float(c["a"]), float(c["b"]), c.get("cut", [])); net = sum(e - s for s, e in keep)
    return net * (2 if keep and clip_parts(c, keep, net) else 1)

class RenderSession:
    """Один рендер: проєкт, тимчасова тека з картинками елементів і шрифтами, запис в історії рендерів проєкту."""
    def __init__(self, pid, elements, cues, out_dir, tmp):
        self.pid, self.cues, self.tmp, self.made, self.used, self.partial = pid, cues, tmp, {}, set(), None
        self.elements = [e for e in elements if e["type"] in ART or e["type"] in RENDERED]
        pr = load_project(pid); self.src = pr["video"]; self.sw, self.sh, _, self.na = probe(self.src); _, self.args = pick_encoder()
        self.canvas = tuple(pr.get("canvas") or CANVAS)
        self.subs_all = [e for e in self.elements if e["type"] == "subs"]; self.subs = any(on(e) for e in self.subs_all)   # кожен спікер — свій елемент «Субтитри»
        self.name, self.out = out_name(pr), Path(out_dir); self.out.mkdir(parents=True, exist_ok=True)   # тека, яку обрав користувач
        self.rec = dict(id=JOB["id"], date=time.time(), out=str(self.out), files=[])

    def save(self): update_project(self.pid, lambda p: p.__setitem__("renders", [self.rec] + [r for r in p["renders"] if r["id"] != self.rec["id"]]))

    def pics(self, e):
        """Картинки елемента для ffmpeg: [(роль, файл, розмір)]; однаковий вигляд не малюємо двічі. Не глобальний у кліпі елемент має свої."""
        key = json.dumps({k: v for k, v in e.items() if k not in OWN_LOOK}, sort_keys=True, default=str)
        if key in self.made: return self.made[key]
        out = []
        def add(role, img): p = Path(self.tmp, f"{len(self.made)}_{role}.png"); img.save(p); out.append((role, str(p), img.size))
        if e["type"] in ART: add("art", art(e)[0])
        if e["type"] in ("video", "cam"):
            mask, ring = frame(e, *layer(e, self.sw, self.sh)[1:])
            if mask: add("mask", mask)
            if ring: add("ring", ring)
        self.made[key] = out; return out

    def copy_fonts(self):
        """Шрифти субтитрів — поруч із файлом ASS: ffmpeg бере їх з робочої теки."""
        own = {pick_font((q.get("own") or {}).get("font") or cue_owner(q, self.subs_all).get("font"))[1] for q in self.cues if q.get("own") and self.subs_all}
        for fp in {pick_font(e.get("font"))[1] for e in self.subs_all if on(e)} | own: shutil.copy(fp, self.tmp)

    def file_for(self, c):
        """Файл шорту: назва проєкту й час початку; той самий кліп ще раз — з номером."""
        ca = float(c["a"]); stem = base = f"{self.name} {int(ca // 60):02d}-{int(ca % 60):02d}"
        while stem in self.used: stem = f"{base} ({len([u for u in self.used if u.startswith(base)]) + 1})"
        self.used.add(stem); return self.out / f"{stem}.mp4"

    def inputs(self, cel, first):
        """Картинки елементів, маски й рамки відео кліпу: (id, роль, файл), розміри картинок, номери входів ffmpeg (з first: перед ними — шматки відео)."""
        pngs, sizes = [], {}
        for e in (e for e in cel if on(e)):
            for role, path, size in self.pics(e):
                pngs.append((e["id"], role, path))
                if role == "art": sizes[e["id"]] = size
        return pngs, sizes, {(eid, role): n for n, (eid, role, _) in enumerate(pngs, first)}

    def encode_clip(self, i, n, c, keep, cel, dst, say, t0):
        """Кодування кліпу в dst: відео з кадруванням, елементи, субтитри, музика. Повертає, чи є звук."""
        a, b, net = keep[0][0], keep[-1][1], sum(e - s for s, e in keep)
        pngs, sizes, inp = self.inputs(cel, len(keep))
        if self.subs: Path(self.tmp, "subs.ass").write_text(subs_ass([q for q in self.cues if q["b"] > a and q["a"] < b], keep, self.subs_all, self.canvas), "utf-8")
        inputs = [x for _, role, p in pngs for x in ["-loop", "1", *(["-t", f"{b - a:.3f}"] if role == "mask" else []), "-i", p]]  # alphamerge не завершиться з нескінченною маскою
        parts = music_parts(cel, net)
        inputs += [x for path, off, _, length, *_ in parts for x in ["-ss", f"{off:.3f}", "-t", f"{length + .1:.3f}", "-i", path]]
        vvol = float(next((e for e in self.elements if e["type"] == "video"), {}).get("vol", 1))
        main = ("ca" if len(keep) > 1 else "am" if self.na > 1 else "0:a") if self.na else None
        afx, alabel = audio_filter(main, parts, len(keep) + len(pngs), vvol, net) if parts or vvol != 1 else ([], None)
        got = lambda k: lambda f: report("render", f"Кліп {i} з {n} · завантажую з Twitch", min(.99, (k + f) / len(keep)), t0)
        video = [x for k, (s, e) in enumerate(keep) for x in local_input(self.src, "best", s, e, got(k))]   # лише те, що лишилось після вирізання
        encode([*video, *inputs,
                "-filter_complex", ";".join([build_filter(self.sw, self.sh, cel, keep, self.na, inp, sizes, bool(self.subs), self.canvas), *afx]),
                "-map", "[v]", "-map", f"[{alabel}]" if alabel else f"[{main}]" if main in ("ca", "am") else "0:a?", *self.args,
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], net, say, cwd=self.tmp)
        return bool(alabel or self.na)

    def clip(self, i, n, c, say, t0):
        """Шорт з кліпу: кодування, перестановка хука чи петлі, мініатюра, запис в історії."""
        cel = clip_elements(self.elements, c); keep = kept(float(c["a"]), float(c["b"]), c.get("cut", []))
        if not keep: raise RuntimeError(f"Кліп {i} вирізано повністю")
        net = sum(e - s for s, e in keep); order = clip_parts(c, keep, net)
        bars = [e for e in cel if e["type"] == "progress" and on(e)] if order else []   # з хуком чи петлею прогрес малюється вже після перестановки
        self.partial = dst = self.file_for(c)
        sound = self.encode_clip(i, n, c, keep, [e for e in cel if e not in bars], dst, say, t0)
        total = rearrange(dst, order, bars, self.args, sound, self.canvas[0], lambda s: say(net + s)) if order else net
        thumb = THUMBS / f"{self.rec['id']}_{i:02d}.jpg"
        run([ffbin("ffmpeg"), "-y", "-v", "error", "-ss", "1", "-i", str(dst), "-frames:v", "1", "-vf", "scale=270:-2", str(thumb)])
        self.rec["files"].append(dict(path=str(dst), thumb=str(thumb), a=float(c["a"]), b=float(c["b"]), len=total)); self.save(); self.partial = None

def render(pid, clips, elements, cues, out_dir, task):
    """Рендер усіх увімкнених кліпів у теку out_dir; поступ — у рядку task, підсумок — у JOB. Скасували — недороблений кліп геть, готові лишаються."""
    TASK.begin(task); session = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            session = RenderSession(pid, elements, cues, out_dir, tmp); session.save(); JOB["out"] = str(session.out); session.copy_fonts()
            todo = [c for c in clips if c.get("on", True)]; units = [clip_work(c) for c in todo]; total, t0 = max(.1, sum(units)), time.time()
            for i, c in enumerate(todo, 1):
                done = sum(units[:i - 1]); say = lambda s, i=i, d=done: report("render", f"Кліп {i} з {len(todo)}", min(.99, (d + s) / total), t0)
                say(0); session.clip(i, len(todo), c, say, t0)
            learn("render", sum(units), t0)
    except Cancelled:
        JOB["cancelled"] = True
        if session and session.partial: session.partial.unlink(missing_ok=True)
    except Exception as e: JOB["err"] = str(e)
    finally: JOB["running"] = False; TASK.finish(task)

def start(pid, clips, elements, cues, music, out, task):
    """Почати рендер у фоні; поступ — у рядку завдання task, підсумок — у JOB."""
    if JOB["running"]: raise HttpError(409, "Рендер уже йде")
    if not out: raise HttpError(400, "Не обрано теку для шортів")
    update_project(pid, lambda pr: pr.update(clips=clips, elements=elements, cues=cues, music=music))
    JOB.update(running=True, n=sum(c.get("on", True) for c in clips), err="", out="", cancelled=False,
               id=uuid.uuid4().hex[:10], project=pid, task=task or uuid.uuid4().hex)
    threading.Thread(target=render, args=(pid, clips, elements, cues, out, JOB["task"]), daemon=True).start()
    TASK.begin(None)                                               # рядок поступу тепер веде потік рендеру: запит, закінчуючись, його не прибирає
    return JOB
