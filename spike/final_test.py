"""Финальный тест ввода в геймплее с точным детектом старта.

Детектор геймплея: белый крест «КОМБО» в области (95,940)-(160,1010) —
в игре ~462 белых пикселя, в меню/загрузке их 0.
Круг №4 (3740 мс) -> экран (901, 1069); курсор ставим туда заранее.
"""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOX_CROSS = (95, 940, 160, 1010)
BOX_BACK = (30, 1000, 360, 1080)


def grab() -> Image.Image:
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white_count(img, box):
    crop = img.crop(box)
    return sum(1 for r, g, b in crop.getdata() if r > 190 and g > 190 and b > 190)


def pink_count(img, box):
    crop = img.crop(box)
    return sum(1 for r, g, b in crop.getdata() if r > 180 and g < 90 and b > 100)


def in_menu(img) -> bool:
    return pink_count(img, BOX_BACK) > 5000


def in_game(img) -> bool:
    return white_count(img, BOX_CROSS) > 200


hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

for attempt in range(4):
    img = grab()
    if in_menu(img):
        print('в меню')
        break
    print('не меню -> Esc')
    idrv.key(27)
    time.sleep(1.6)
else:
    print('не удалось попасть в меню')
    sys.exit(1)

idrv.move_absolute(901, 1069)  # курсор на круг №4 заранее
idrv.click(1810, 1005)         # Play
t0 = time.perf_counter()
print('клик Play')

t_start = None
while time.perf_counter() - t0 < 25.0:
    img = grab()
    if in_game(img):
        t_start = time.perf_counter()
        break
    time.sleep(0.06)

if t_start is None:
    print('геймплей не начался за 25 с')
    idrv.shot('33_stuck')
    sys.exit(2)

print('детект геймплея: t=%.2f c от Play' % (t_start - t0))

target = t_start + 3.40
while time.perf_counter() < target:
    time.sleep(0.004)

n = 0
while time.perf_counter() < target + 1.2:
    idrv.key(0x5A)  # Z
    n += 1
    time.sleep(0.007)
print('нажатий Z в окне ноты №4:', n)

time.sleep(0.3)
print('снимок:', idrv.shot('33_final'))
