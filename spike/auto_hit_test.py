"""Автотест ввода в геймплее: детект старта карты по экрану, затем прицельные Z.

Детектор: в меню внизу слева — розовая кнопка «Назад» (~19k розовых пикселей),
в геймплее — их нет (0). Старт карты = момент, когда розовые исчезли.
Круг №4 (3740 мс) = экран (901, 1069); курсор ставим туда заранее.
"""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOX = (30, 1000, 360, 1080)  # область кнопки «Назад»


def pink_count(img: Image.Image) -> int:
    crop = img.crop(BOX)
    return sum(1 for r, g, b in crop.getdata() if r > 180 and g < 90 and b > 100)


def grab() -> Image.Image:
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def in_menu(img: Image.Image) -> bool:
    return pink_count(img) > 5000


hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

# привести к меню: если игра/пауза — Esc
for attempt in range(3):
    img = grab()
    p = pink_count(img)
    print('состояние: розовых=%d -> %s' % (p, 'меню' if p > 5000 else 'не меню'))
    if p > 5000:
        break
    idrv.key(27)  # Esc
    time.sleep(1.6)

if not in_menu(grab()):
    print('Не удалось вернуться в меню — стоп')
    sys.exit(1)

# курсор заранее на круг №4
idrv.move_absolute(901, 1069)

# Play
idrv.click(1810, 1005)
t0 = time.perf_counter()
print('клик Play')

# ждём старта карты: розовая кнопка исчезает
t_start = None
while time.perf_counter() - t0 < 20.0:
    img = grab()
    if pink_count(img) < 500:
        t_start = time.perf_counter()
        break
    time.sleep(0.08)

if t_start is None:
    print('Карта не стартовала за 20 с — стоп')
    idrv.shot('32_stuck')
    sys.exit(2)

print('детект старта карты: t=%.2f с от Play' % (t_start - t0))

# ждём окно ноты №4 (3740 мс) и долбим Z
target = t_start + 3.55
while time.perf_counter() < target:
    time.sleep(0.005)

n = 0
while time.perf_counter() < target + 1.1:
    idrv.key(0x5A)  # Z
    n += 1
    time.sleep(0.008)
print('нажатий Z в окне ноты:', n)

time.sleep(0.4)
print('снимок:', idrv.shot('32_z_auto'))
