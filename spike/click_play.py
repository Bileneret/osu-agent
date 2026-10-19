"""Поиск кнопки «играть» по цвету и клик по её актуальному центру.

Меню lazer анимируется при наведении: логотип и кнопки сдвигаются, поэтому
координаты надо брать со СВЕЖЕГО кадра с уже установленным hover.
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


def find_purple(img, y0=480, y1=720):
    """Bbox фиолетовой кнопки (фиолетовый: B высокий, R средний, G низкий)."""
    crop = img.crop((0, y0, img.width, y1))
    px = crop.load()
    xs, ys = [], []
    for y in range(0, crop.height, 3):
        for x in range(0, crop.width, 3):
            r, g, b = px[x, y]
            if b > 170 and 70 < r < 180 and g < 120 and (b - g) > 80:
                xs.append(x)
                ys.append(y + y0)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

# панель меню показывается при движении мыши — «встряхнём» курсор
for step in range(6):
    idrv.move_absolute(700 + step * 60, 600)
    time.sleep(0.05)
time.sleep(0.4)

img = grab()
img.save('spike/shots/80_menu_hover.png')
box = find_purple(img)
print('bbox фиолетовой кнопки:', box)
if box:
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    print('клик в центр:', cx, cy)
    idrv.click(cx, cy)
    time.sleep(3)
    print('снимок:', idrv.shot('80_after_click'))
else:
    print('кнопка не найдена — снимок для разбора сохранён')
