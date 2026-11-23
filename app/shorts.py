#!/usr/bin/env python3
"""ReCut — точка входу: сервер інтерфейсу або (з --stt-worker) окремий процес розпізнавання мови."""
import sys
try: import truststore; truststore.inject_into_ssl()   # HTTPS перевіряє сама Windows, як браузер: докачує відсутні корені (інакше на старих системах «certificate has expired»)
except ImportError: pass                           # середовище без пакета (розробка) — звичайна перевірка Python
from recut.server import main
from recut.stt import stt_worker


if __name__ == "__main__":
    if "--stt-worker" in sys.argv: i = sys.argv.index("--stt-worker"); stt_worker(sys.argv[i + 1], (sys.argv[i + 2:] or ["large-v3-turbo"])[0])
    else: main()
