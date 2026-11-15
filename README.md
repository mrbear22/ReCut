# ShortsMaker

Вертикальні шорти зі стрімів: пошук моментів, субтитри, плашки й вебкамера, рендер і черга публікацій у TikTok та YouTube через Buffer.

## Встановлення

Завантаж **ShortsMaker-Setup.exe** з [Releases](https://github.com/mrbear22/ShortsMaker/releases/latest), запусти й обери теку.
Нові версії програма знаходить сама: у шапці з'являється кнопка «Оновити».

Готові шорти лежать у теці програми: `renders\<проєкт>\`. Проєкти, моделі й налаштування — у `data\`.

Важке завантажується лише коли вперше знадобиться: модель розпізнавання мови (1.6 ГБ), бібліотеки CUDA для NVIDIA (1.3 ГБ),
локальний ШІ для описів (~5 ГБ). Усе працює локально й безкоштовно.

## Клавіші на таймлайні

| | |
|---|---|
| `Ctrl` + тягни | область аналізу |
| `Shift` + тягни | новий кліп; у рядку реплік — нова репліка |
| `Alt` + тягни по кліпу | вирізати шматок (ПКМ — повернути) |
| `Ctrl+C` / `Ctrl+V` / `Ctrl+D` | копіювати / вставити / дублювати |
| `Del` | видалити вибране |
| ПКМ | меню дій з кліпом, реплікою, елементом, областю чи рамкою |
| `Shift` / `Ctrl` у кадруванні | тримати пропорції / вимкнути прилипання |

## Розробка

Запуск із сорсів (Python 3.12+ і ffmpeg з libass у PATH; дані в `app\data`, рендери в `app\renders`, оновлення вимкнені):

    pip install numpy pillow "opencv-python-headless<5" faster-whisper
    python app/shorts.py

Збірка (Git Bash, Inno Setup 6):

    ./build.sh        →  dist/ShortsMaker-Setup.exe

Новий реліз: підняти `VERSION` в `app/shorts.py`, закомітити, зібрати й викласти:

    gh release create v1.2.3 dist/ShortsMaker-Setup.exe

Програма порівнює свій тег з новим релізом через GitHub. Змінились лише файли в `app/` — завантажує тільки їх;
змінились `build.sh`, `installer.iss` чи `launcher/` — тихо ставить новий інсталятор.

- `app/shorts.py` — сервер: проєкти, аналіз, розпізнавання мови, рендер
- `app/ui.html`, `app/publish.js` — інтерфейс; `app/publish.py` — Buffer і сховище відео
- `cloudflare/worker.js` — сховище відео для Buffer (Cloudflare R2)
- `launcher/` — `ShortsMaker.exe`; `installer.iss` — інсталятор
