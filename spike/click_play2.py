"""Показать панель меню и кликнуть «играть» — всё в одном процессе.

Панель главного меню lazer видна считанные секунды после активности,
а между отдельными запусками Python проходит 2–4 с — поэтому всё в одном скрипте.
"""
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


def find_button(img, y0=520, y1=680):
    """Ищем цветные кнопки меню: фиолетовую (играть) и оранжевую (редактировать)."""
    crop = img.crop((0, y0, img.width, y1))
    px = crop.load()
    purple, orange = [], []
    for y in range(0, crop.height, 2):
        for x in range(0, crop.width, 2):
            r, g, b = px[x, y]
            if b > 200 and 90 < r < 170 and g < 90:
                purple.append((x, y + y0))
            if r > 200 and 120 < g < 190 and b < 80:
                orange.append((x, y + y0))
    def box(pts):
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    return box(purple), box(orange)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
time.sleep(0.3)

idrv.key(0x5A)  # Z — тап покажет панель меню
time.sleep(0.35)

img = grab()
img.save('spike/shots/81_menu.png')
purple, orange = find_button(img)
print('фиолетовая (играть):', purple)
print('оранжевая (редактировать):', orange)

if purple:
    cx, cy = (purple[0] + purple[2]) // 2, (purple[1] + purple[3]) // 2
    print('клик в', cx, cy)
    idrv.click(cx, cy)
    time.sleep(3.0)
    print('снимок:', idrv.shot('81_after'))
else:
    print('кнопка не найдена')
