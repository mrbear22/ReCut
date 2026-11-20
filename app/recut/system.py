"""Система: діалоги вибору, вікно Edge, перезапуск і оновлення."""
import base64, json, os, re, subprocess, threading, time, urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import datetime
from pathlib import Path
from .analysis import AI
from .core import CFG, CODE_VERSION, DATA, HERE, ROOT, SYS_ENV, run
from .stt import STT

# ── системні дії ──
DIALOG_EN = {"Відео": "Video", "Музика": "Music", "Зображення": "Images", "Усі": "All", "Куди зберегти шорти": "Where to save the shorts", "Рендерити сюди": "Render here"}
dialog_text = lambda s: DIALOG_EN.get(s, s) if CFG.get("lang") == "en" else s   # системні діалоги — мовою інтерфейсу (решту тексту перекладає сторінка)

def ask_file(kind):
    flt = {"video": ("Відео|*.mp4;*.mov;*.mkv;*.webm;*.flv;*.ts", "*.mp4 *.mov *.mkv *.webm *.flv *.ts"),
           "audio": ("Музика|*.mp3;*.wav;*.m4a;*.ogg;*.flac;*.aac;*.opus", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.opus")}.get(
          kind, ("Зображення|*.png;*.jpg;*.jpeg;*.webp;*.bmp", "*.png *.jpg *.jpeg *.webp *.bmp"))
    flt = (dialog_text(flt[0].split("|")[0]) + "|" + flt[0].split("|", 1)[1], flt[1])
    if os.name == "nt": return win_dialog(f"$d=New-Object System.Windows.Forms.OpenFileDialog;$d.Filter='{flt[0]}|{dialog_text('Усі')}|*.*';if($d.ShowDialog($o) -eq 'OK'){{$p=$d.FileName}}")
    import tkinter as tk; from tkinter import filedialog
    t = tk.Tk(); t.withdraw(); t.attributes("-topmost", True)
    p = filedialog.askopenfilename(parent=t, filetypes=[(kind, flt[1]), ("*", "*.*")]); t.destroy(); return p

FOLDER_CS = r'''using System; using System.Runtime.InteropServices;
public static class FolderPick {
  [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialog {}
  [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileDialog {
    [PreserveSig] int Show(IntPtr owner);
    void SetFileTypes(uint n, IntPtr specs); void SetFileTypeIndex(uint i); void GetFileTypeIndex(out uint i);
    void Advise(IntPtr sink, out uint cookie); void Unadvise(uint cookie);
    void SetOptions(uint fos); void GetOptions(out uint fos);
    void SetDefaultFolder(IShellItem si); void SetFolder(IShellItem si);
    void GetFolder(out IShellItem si); void GetCurrentSelection(out IShellItem si);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name); void GetFileName(out IntPtr name);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title); void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label); void GetResult(out IShellItem si);
  }
  [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv); void GetParent(out IShellItem si);
    void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
  }
  [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
  static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IShellItem item);
  public static string Pick(IntPtr owner, string title, string ok, string start) {
    var d = (IFileDialog)new FileOpenDialog(); uint o; d.GetOptions(out o); d.SetOptions(o | 0x20 | 0x40);   // теки, лише справжні шляхи
    d.SetTitle(title); d.SetOkButtonLabel(ok);
    if (!string.IsNullOrEmpty(start)) try { IShellItem f; SHCreateItemFromParsingName(start, IntPtr.Zero, typeof(IShellItem).GUID, out f); d.SetFolder(f); } catch {}
    if (d.Show(owner) != 0) return "";
    IShellItem r; d.GetResult(out r); string p; r.GetDisplayName(0x80058000, out p); return p;
  }
}'''                                                                   # сучасний діалог вибору теки (IFileOpenDialog), не старе дерево FolderBrowserDialog

def ask_dir(start):
    """Тека для рендеру або '' — користувач передумав."""
    if os.name == "nt":
        b64 = lambda s: base64.b64encode(s.encode("utf-8")).decode()
        txt = lambda s: f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64(s)}'))"   # кирилиця й лапки в шляху не ламають команду
        return win_dialog(f"Add-Type -TypeDefinition @'\n{FOLDER_CS}\n'@\n$p=[FolderPick]::Pick($o.Handle,{txt(dialog_text('Куди зберегти шорти'))},{txt(dialog_text('Рендерити сюди'))},{txt(start)})")
    import tkinter as tk; from tkinter import filedialog
    t = tk.Tk(); t.withdraw(); t.attributes("-topmost", True)
    p = filedialog.askdirectory(parent=t, initialdir=start, title=dialog_text("Куди зберегти шорти")); t.destroy(); return p

def win_dialog(body):
    """Системний діалог Windows через PowerShell: body кладе вибраний шлях у $p, власник діалогу — $o. Повертає шлях або ''."""
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          # невидимий власник «поверх усіх»: фоновий процес не може вивести діалог наперед, а власник-topmost — може
          "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false;Opacity=0;StartPosition='CenterScreen'};"
          "$o.Show();$o.Activate();$p='';" + body + "\nif($p){[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p))}")
    r = run(["powershell", "-NoProfile", "-STA", "-EncodedCommand", base64.b64encode(ps.encode("utf-16-le")).decode()])
    out = r.stdout.decode("ascii", "ignore").strip()                    # base64 — кирилиця в шляху не ламається
    return base64.b64decode(out).decode("utf-8") if out else ""
# ── оновлення з GitHub: що змінилось між нашим тегом і новим релізом, видно з порівняння комітів ──
LINKS = {"patreon": "https://www.patreon.com/miishanii"}             # підтримка автора; програма безкоштовна повністю

def reveal(path):
    if os.name == "nt": subprocess.Popen(["explorer", "/select,", path] if Path(path).is_file() else ["explorer", path])
    else: subprocess.Popen(["xdg-open", str(Path(path).parent if Path(path).is_file() else path)])

def open_window(url):
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        edge = Path(base or "-", "Microsoft/Edge/Application/msedge.exe")
        if edge.is_file():                                         # вікно-застосунок без панелей браузера
            return subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={DATA / 'window'}", "--no-first-run",
                                     "--no-default-browser-check", "--window-size=1500,950",
                                     "--disable-extensions", "--disable-sync", "--disable-features=msImplicitSignin"], env=SYS_ENV)   # розширення з акаунта Edge (темні теми тощо) перефарбовують програму
    webbrowser.open(url)

class Windows:
    """Відкриті вікна програми: кожне озивається (ping) і прощається (bye); без вікон програма не потрібна."""
    def __init__(self): self.seen, self.started, self.tied = {}, time.time(), True   # tied — програма живе, поки є вікна (без --no-window)

    def ping(self, page): self.seen[page] = time.time()

    def bye(self, page):
        """True — закрили останнє відоме вікно (невідоме — сторінка до перезапуску після оновлення)."""
        return self.seen.pop(page, None) is not None and not self.seen and self.tied

    def prune(self, silent):
        for k, t in list(self.seen.items()):
            if time.time() - t > silent: self.seen.pop(k, None)

    def none_for(self, grace): return not self.seen and time.time() - self.started > grace

WINDOWS = Windows()
PAGE_SILENT_S = 150                                               # вікно, що зникло без «бувай» (браузер вбили): згорнуте браузер будить рідко, тож чекаємо довше

def quit_app():
    """Вікна немає — виходимо повністю, разом з рендером, ffmpeg і локальним ШІ: без вікна користувачеві це вже не потрібно."""
    AI.stop()
    if os.name == "nt": run(["taskkill", "/F", "/T", "/PID", str(os.getpid())])   # /T — з усіма дочірніми процесами
    os._exit(0)

def watchdog():                                                    # запасний шлях: звичайне закриття вікна обробляє /api/bye миттєво
    while True:
        time.sleep(1)
        WINDOWS.prune(PAGE_SILENT_S)
        if WINDOWS.none_for(60): quit_app()               # при старті даємо вікну хвилину відкритись

def detached(*cmd):
    """Процес, що переживе цей: не дочірній (через start), тож taskkill /T у quit_app його не зачепить."""
    subprocess.Popen(["cmd", "/c", "start", "", *cmd], creationflags=0x08000000)   # CREATE_NO_WINDOW

def finish_update(setup):
    """Код замінено — запускаємо нову версію без нового вікна (сторінка перезавантажиться сама) і виходимо.
    Потрібен інсталятор — закриваємо вікно й ставимо тихо; інсталятор сам відкриє програму."""
    time.sleep(.5)                                                # відповідь має дійти до сторінки
    if setup: run(["powershell", "-NoProfile", "-Command",
                   f"Get-CimInstance Win32_Process -Filter \"name='msedge.exe'\" | ? {{ $_.CommandLine -like '*{str(DATA / 'window')}*' }} | % {{ Stop-Process -Id $_.ProcessId -Force }}"])
    if setup: detached(str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    else: detached(str(ROOT / "runtime" / "pythonw.exe"), str(HERE / "shorts.py"), "--restart")
    time.sleep(1.5)                                               # cmd має встигнути запустити процес і вийти, інакше taskkill /T забере і його
    if setup: quit_app()                                          # інсталятор сам відкриє програму
    AI.stop(); STT.stop(); os._exit(0)                            # без taskkill /T: вікно Edge — наш дочірній процес, воно лишається й перезавантажиться

def reopen_window(url):
    """Старе вікно не озвалось після оновлення (його закрила попередня версія) — відкриваємо нове."""
    time.sleep(8)
    if not WINDOWS.seen and (w := open_window(url)): threading.Thread(target=watch_window, args=(w,), daemon=True).start()

def window_icon():
    """Edge дає вікну-застосунку фавікон 16 px, і панель задач його розтягує до розмитого — ставимо вікну наш значок у потрібному розмірі.
    Edge може повернути свій (перезавантаження сторінки), тож перевіряємо раз на кілька секунд."""
    import ctypes
    from ctypes import wintypes as W
    u = ctypes.windll.user32
    u.LoadImageW.restype = W.HANDLE; u.SendMessageW.restype = ctypes.c_ssize_t; u.SendMessageW.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    dpi = getattr(u, "GetDpiForSystem", lambda: 96)()
    big, small = (u.LoadImageW(None, str(HERE / "favicon.ico"), 1, n * dpi // 96, n * dpi // 96, 0x10) for n in (24, 16))   # кнопка панелі задач — 24 px: свій кадр без масштабування
    if not big: return
    buf, found = ctypes.create_unicode_buffer(64), []
    def ours(h, _):                                                # вікно Edge з нашою сторінкою
        if u.IsWindowVisible(h) and u.GetClassNameW(h, buf, 64) and buf.value == "Chrome_WidgetWin_1" and u.GetWindowTextW(h, buf, 64) and buf.value == "ReCut": found.append(h)
        return True
    enum = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)(ours)
    while True:
        found.clear(); u.EnumWindows(enum, 0)
        for h in found:
            if u.SendMessageW(h, 0x7F, 1, 0) != big: u.SendMessageW(h, 0x80, 1, big); u.SendMessageW(h, 0x80, 0, small)   # WM_GETICON / WM_SETICON
        time.sleep(2)

def watch_window(proc):
    """Процес вікна Edge завершився — вікно закрили. Якщо він вийшов за секунди, це не наше вікно: Edge передав його вже запущеному."""
    t0 = time.time(); proc.wait()
    if time.time() - t0 > 5: quit_app()

def port_owner(port):
    """PID процесу, що слухає порт (Windows)."""
    m = re.search(rf"127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)", run(["netstat", "-ano", "-p", "TCP"], text=True).stdout)
    return int(m.group(1)) if m else None

def stop_old_server(url):
    """На порту інша версія ReCut, що не рендерить, — зупиняємо її, щоб оновлення почало працювати одразу.
    True, якщо зупинили; False — лишаємо як є (та сама версія, йде рендер, чужа програма або не Windows)."""
    get = lambda path: json.loads(urllib.request.urlopen(url + path, timeout=3).read())
    try: busy = get("/api/status")["running"]
    except Exception: return False                              # порт зайняв не ReCut
    try: same = get("/api/version").get("version") == CODE_VERSION
    except Exception: same = False                              # версії до цієї не знають /api/version
    pid = None if same or busy or os.name != "nt" else port_owner(CFG["port"])
    if not pid or pid == os.getpid(): return False
    print(datetime.now(), "stopping old version, PID", pid); return run(["taskkill", "/F", "/T", "/PID", str(pid)]).returncode == 0   # /T — разом з її локальним ШІ
