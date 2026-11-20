#!/usr/bin/env python3
"""ReCut — точка входу: сервер інтерфейсу або (з --stt-worker) окремий процес розпізнавання мови."""
import sys
from recut.server import main
from recut.stt import stt_worker


if __name__ == "__main__":
    if "--stt-worker" in sys.argv: i = sys.argv.index("--stt-worker"); stt_worker(sys.argv[i + 1], (sys.argv[i + 2:] or ["large-v3-turbo"])[0])
    else: main()
