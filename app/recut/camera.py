"""Пошук вебкамери в кадрах з плеєра."""
import base64
import numpy as np
from .libs import CV_LIBS, need_libs

# ── пошук вебкамери ──
def detect_cam(shots):
    """Вебкамера: обличчя (Haar) у кадрах з плеєра (JPEG, 640 px); межі — найсильніші біля обличчя лінії, що є в кожному кадрі (рамка оверлею).
    Рамки не видно — кадр «голова й плечі» навколо обличчя."""
    need_libs(CV_LIBS, "cv2", "Завантажую OpenCV, 40 МБ")
    import cv2
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    frames = [g for g in (cv2.imdecode(np.frombuffer(base64.b64decode(s.split(",", 1)[-1]), np.uint8), cv2.IMREAD_GRAYSCALE) for s in shots) if g is not None]
    if not frames: raise RuntimeError("Не вдалося прочитати кадри")
    ah, aw = frames[0].shape; frames = [g for g in frames if g.shape == (ah, aw)]
    faces = [(x + w / 2, y + h / 2, w) for g in frames for x, y, w, h in casc.detectMultiScale(g, 1.1, 6, minSize=(18, 18))]
    if len(faces) < max(2, len(frames) * .25): return None
    F = np.array(faces); near = lambda f: np.hypot(*(F[:, :2] - f[:2]).T) < f[2] * .6
    cx, cy, fw = np.median(F[near(max(F, key=lambda f: near(f).sum()))], axis=0)   # найчастіше місце обличчя
    vert, horz = (cv2.GaussianBlur(np.min([np.abs(cv2.Sobel(g, cv2.CV_32F, *d)) for g in frames], 0), (0, 0), 1) for d in ((1, 0), (0, 1)))   # межі, що є в кожному кадрі
    def side(prof, a, b, default):
        lo, hi = sorted((max(0, int(a)), max(0, int(b)))); seg = prof[lo:hi]
        return lo + int(np.argmax(seg)) if len(seg) and seg.max() > 30 else default
    vx = vert[max(0, int(cy - fw)):int(cy + fw)].mean(0); hy = horz[:, max(0, int(cx - fw)):int(cx + fw)].mean(1)
    L, R = side(vx, cx - 5 * fw, cx - .8 * fw, cx - 2.2 * fw), side(vx, cx + .8 * fw, cx + 5 * fw, cx + 2.2 * fw)
    T, Bt = side(hy, cy - 4 * fw, cy - .8 * fw, cy - 1.5 * fw), side(hy, cy + .8 * fw, cy + 4 * fw, cy + 2.2 * fw)
    L, T, R, Bt = max(0, L), max(0, T), min(aw, R), min(ah, Bt)
    return [L / aw, T / ah, (R - L) / aw, (Bt - T) / ah]
