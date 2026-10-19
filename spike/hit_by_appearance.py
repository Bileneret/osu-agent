"""Первый хит без знания S: детект появления ноты на экране и тап через preempt.

Нота-круг №4 (3740 мс, координата osu (235,380) -> экран (901,1069))
проявляется за preempt (AR3 -> 1440 мс) до своего времени. Ловим момент
появления по яркости в области ноты и тапаем через (preempt - 40 мс).
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
# область вокруг круга №4 на экране (901,1069), радиус ~100 px
NOTE_BOX = (801, 969, 1001, 1079)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


def bright(img):
    crop = img.crop(NOTE_BOX)
    return sum(1 for r, g, b in crop.getdata() if r > 170 and g > 170 and b > 170)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

# привести к song select
for _ in range(4):
    img = grab()
    if pink(img) > 5000:
        print('song select')
        break
    idrv.key(27)
    time.sleep(1.5)

if pink(grab()) <= 5000:
    print('не song select — стоп')
    sys.exit(1)

PREEMPT = 1.440  # мс -> с (AR3 в lazer)

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
print('Play')

# ждём HUD
t_hud = None
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        t_hud = time.perf_counter()
        break
    time.sleep(0.05)
if t_hud is None:
    print('карта не стартовала')
    sys.exit(2)
print('HUD на %.2f c' % (t_hud - t0))

# курсор пока держим в стороне, чтобы не мешать детекту
idrv.move_absolute(960, 200)

# ждём появления ноты в её области (яркость скакнёт)
base = bright(grab())
print('фон области: %d ярких' % base)
t_appear = None
while time.perf_counter() - t_hud < 12:
    b = bright(grab())
    if b > base + 250:
        t_appear = time.perf_counter()
        break
    time.sleep(0.02)

if t_appear is None:
    print('нота не замечена')
    idrv.shot('95_note_not_seen')
    sys.exit(3)

print('нота появилась: t=%.2f c от HUD, яркость %d' % (t_appear - t_hud, b))

# перед тапом переносим курсор на ноту
idrv.move_absolute(901, 1069)

# тапаем через preempt - 40 мс
t_tap = t_appear + PREEMPT - 0.040
while time.perf_counter() < t_tap - 0.002:
    pass
idrv.key(0x5A)
print('тап: t=%.3f c от HUD' % (time.perf_counter() - t_hud))

time.sleep(0.5)
print('снимок:', idrv.shot('95_after_tap'))
