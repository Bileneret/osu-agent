"""Адаптивный клик по «играть»: hover -> пауза -> перепроверка позиции -> клик."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def find_purple(img, y0=500, y1=700):
    crop = img.crop((0, y0, img.width, y1))
    px = crop.load()
    pts = []
    for y in range(0, crop.height, 2):
        for x in range(0, crop.width, 2):
            r, g, b = px[x, y]
            if b > 200 and 90 < r < 170 and g < 90:
                pts.append((x, y + y0))
    if len(pts) < 50:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
time.sleep(0.3)

# показать панель
idrv.key(0x5A)
time.sleep(0.4)

box = find_purple(grab())
print('кнопка (1-й замер):', box)
if not box:
    sys.exit(1)
cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2

# hover и пауза, чтобы анимация меню успокоилась
idrv.move_absolute(cx, cy)
time.sleep(0.9)

box2 = find_purple(grab())
print('кнопка (2-й замер):', box2)
if box2:
    cx2, cy2 = (box2[0] + box2[2]) // 2, (box2[1] + box2[3]) // 2
    if abs(cx2 - cx) > 2 or abs(cy2 - cy) > 2:
        idrv.move_absolute(cx2, cy2)
        time.sleep(0.25)
    print('клик в', cx2, cy2)
    idrv.click(cx2, cy2)
    time.sleep(3.0)
    print('снимок:', idrv.shot('82_after'))
