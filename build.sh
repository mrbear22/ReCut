#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
OUT=dist/ShortsMaker; W=dist/.cache
PY=$(python -c "print('python')" 2>/dev/null || echo python3)   # на Windows python3 — заглушка Microsoft Store
rm -rf "$OUT/runtime" "$OUT/app" "$OUT/ffmpeg"   # data і renders користувача не чіпаємо
mkdir -p "$OUT/runtime/Lib/site-packages" "$OUT/app" "$W"
[ -f "$W/py.zip" ] || curl -sSL -o "$W/py.zip" https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip
# у програмі лише те, без чого вона не стартує; ffmpeg, розпізнавання мови й OpenCV вона завантажує сама, коли вперше знадобляться
rm -rf "$W/wheels"; $PY -m pip download --platform win_amd64 --python-version 3.12 --only-binary=:all: --no-deps numpy pillow -d "$W/wheels" -q
$PY -m pip install -q ziglang
$PY - "$OUT" "$W" <<'PY'
import sys, zipfile, pathlib
out, w = map(pathlib.Path, sys.argv[1:])
zipfile.ZipFile(w / "py.zip").extractall(out / "runtime")
for whl in (w / "wheels").glob("*.whl"): zipfile.ZipFile(whl).extractall(out / "runtime/Lib/site-packages")
next((out / "runtime").glob("python*._pth")).write_text("python312.zip\n.\nLib\\site-packages\n..\\app\nimport site\n")
PY
cp app/shorts.py app/publish.py app/localai.py app/ui.html app/publish.js "$OUT/app/"
(cd launcher && $PY -m ziglang cc -target x86_64-windows-gnu -municode -O2 -s -Wl,--subsystem,windows launcher.c app.rc -o "../$OUT/ShortsMaker.exe")
printf '@echo off\r\n"%%~dp0runtime\\python.exe" "%%~dp0app\\shorts.py"\r\npause\r\n' > "$OUT/ShortsMaker (debug).bat"
VER=$(sed -n 's/^REPO, VERSION = .*"\([0-9.]*\)".*/\1/p' app/shorts.py)   # версія — тег релізу
"${ISCC:-/c/Program Files (x86)/Inno Setup 6/ISCC.exe}" //Q //DAppVersion="$VER" installer.iss
echo "dist/ShortsMaker-Setup.exe (v$VER)"
echo "$OUT"
