#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
OUT=dist/ShortsMaker; W=dist/.cache
PY=$(python -c "print('python')" 2>/dev/null || echo python3)   # на Windows python3 — заглушка Microsoft Store
rm -rf "$OUT/runtime" "$OUT/app" "$OUT/ffmpeg"   # data і renders користувача не чіпаємо
mkdir -p "$OUT/runtime/Lib/site-packages" "$OUT/app" "$OUT/ffmpeg" "$W"
[ -f "$W/py.zip" ] || curl -sSL -o "$W/py.zip" https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip
[ -f "$W/ff.zip" ] || curl -sSL -o "$W/ff.zip" https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip
$PY -m pip download --platform win_amd64 --python-version 3.12 --only-binary=:all: --no-deps numpy pillow "opencv-python-headless<5" -d "$W/wheels" -q
# розпізнавання мови з залежностями; модель і CUDA-бібліотеки програма завантажує сама, коли вперше знадобляться
$PY -m pip download --platform win_amd64 --python-version 3.12 --only-binary=:all: faster-whisper -d "$W/wheels" -q
rm -f "$W"/wheels/nvidia_*.whl
$PY -m pip install -q ziglang
$PY - "$OUT" "$W" <<'PY'
import sys, zipfile, pathlib
out, w = map(pathlib.Path, sys.argv[1:])
zipfile.ZipFile(w / "py.zip").extractall(out / "runtime")
for whl in (w / "wheels").glob("*.whl"): zipfile.ZipFile(whl).extractall(out / "runtime/Lib/site-packages")
next((out / "runtime").glob("python*._pth")).write_text("python312.zip\n.\nLib\\site-packages\n..\\app\nimport site\n")
with zipfile.ZipFile(w / "ff.zip") as z:
    for n in z.namelist():
        if "/bin/" in n and n.lower().endswith((".exe", ".dll")) and not n.lower().endswith("ffplay.exe"):
            (out / "ffmpeg" / pathlib.Path(n).name).write_bytes(z.read(n))
PY
cp app/shorts.py app/publish.py app/localai.py app/update.py app/ui.html app/publish.js "$OUT/app/"
(cd launcher && $PY -m ziglang cc -target x86_64-windows-gnu -municode -O2 -s -Wl,--subsystem,windows launcher.c app.rc -o "../$OUT/ShortsMaker.exe")
printf '@echo off\r\n"%%~dp0runtime\\python.exe" "%%~dp0app\\shorts.py"\r\npause\r\n' > "$OUT/ShortsMaker (debug).bat"
# реліз: інсталятор + app.zip (лише код — для швидкого оновлення з програми) + release.json (версія й RUNTIME)
VER=$($PY -c "import sys; sys.path.insert(0, 'app'); import update; print(update.VERSION)")
if [ "${RELEASE:-1}" = 1 ]; then
  "${ISCC:-/c/Program Files (x86)/Inno Setup 6/ISCC.exe}" //Q //DAppVersion="$VER" installer.iss
  $PY - <<'PY'
import json, sys, zipfile, pathlib
sys.path.insert(0, "app"); import update
with zipfile.ZipFile("dist/app.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for n in update.APP_FILES: z.write(pathlib.Path("app") / n, n)
pathlib.Path("dist/release.json").write_text(json.dumps({"version": update.VERSION, "runtime": update.RUNTIME}))
PY
  echo "dist/ShortsMaker-Setup.exe dist/app.zip dist/release.json (v$VER)"
fi
echo "$OUT"
