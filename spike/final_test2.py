"""Тест ввода в геймплее, версия 2: курсор возвращаем на круг №4 сразу после Play.

Широкое окно долбёжки: от детекта HUD + 1.0 с до + 6.5 с — покрывает ноту №4
(3740 мс) при реальной задержке старта 0.9–1.9 с после детекта.
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


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def counts(img, box):
    crop = img.crop(box)
    white = pink = 0
    for r, g, b in crop.getdata():
        if r > 190 and g > 190 and b > 190:
            white += 1
        elif r > 180 and g < 90 and b > 100:
            pink += 1
    return white, pink


hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

for _ in range(4):
    if counts(grab(), BOX_BACK)[1] > 5000:
        print('в меню')
        break
    idrv.key(27)
    time.sleep(1.6)

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
print('клик Play')

t_start = None
while time.perf_counter() - t0 < 25.0:
    if counts(grab(), BOX_CROSS)[0] > 200:
        t_start = time.perf_counter()
        break
    time.sleep(0.05)

if t_start is None:
    idrv.shot('34_stuck')
    print('геймплей не начался')
    sys.exit(2)

print('детект HUD: t=%.2f c' % (t_start - t0))

# сразу возвращаем курсор на круг №4
idrv.move_absolute(901, 1069)

# долбим Z в широком окне
while time.perf_counter() < t_start + 1.0:
    time.sleep(0.004)
n = 0
while time.perf_counter() < t_start + 6.5:
    idrv.key(0x5A)
    n += 1
    time.sleep(0.006)
print('нажатий Z:', n)

time.sleep(0.3)
print('снимок:', idrv.shot('34_final2'))
