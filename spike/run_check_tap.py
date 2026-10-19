"""Контрольный прогон после исправления координат (проверка от 20.10).

Проверяем: (1) NF включён, (2) карта запускается, (3) клок даёт позицию,
(4) тапы по нотам с исправленной формулой координат и сканированием S (20-150 мс).
"""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, record_loopback, locate
from osu_agent.beatmap import Beatmap
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
OSU_TMP = r'./beatmaps/_ref/pearto.osu'
BOX_CROSS = (95, 940, 160, 1010)
BOX_BACK = (30, 1000, 360, 1080)
STRIP = (60, 10, 900, 230)  # лента событий слева вверху


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
time.sleep(0.3)

# --- подготовка: song select + NF + Play ---
if pink(grab()) < 5000:
    for _ in range(4):
        if pink(grab()) > 5000:
            break
        idrv.key(27)
        time.sleep(1.5)
if pink(grab()) < 5000:
    print('не song select — стоп')
    idrv.shot('97_stuck')
    sys.exit(1)
print('song select')

# включаем No Fail
idrv.click(475, 1043)
time.sleep(1.2)
idrv.click(588, 420)
time.sleep(0.8)
idrv.key(27)
time.sleep(1.0)

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('карта стартовала на %.2f c' % (time.perf_counter() - t0))
        break
    time.sleep(0.05)
else:
    print('карта не стартовала')
    idrv.shot('97_nostart')
    sys.exit(2)

time.sleep(3.0)

# --- клок ---
ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
objs = sorted(bm.hit_objects, key=lambda o: o.time)

rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

# --- серия тапов: разные S ---
S_LIST = [0.03, 0.05, 0.08, 0.12, 0.16, 0.22]
plan = []
now = time.perf_counter()
i = 0
for o in objs:
    if i >= len(S_LIST):
        break
    s = S_LIST[i]
    t_tap = t_ref + (o.time / 1000.0 - s - m.position_sec)
    if t_tap < now + 1.0:
        continue
    plan.append((o, s, t_tap))
    i += 1

print('план: %d тапов' % len(plan))
strips = []
for k, (o, s, t_tap) in enumerate(plan):
    wait = t_tap - 0.5
    nw = time.perf_counter()
    if wait > nw:
        time.sleep(wait - nw)
    sx, sy = idrv.osu_to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap:
        pass
    idrv.tap(0x5A)
    print('  %d: %s %.0f мс | S=%.2f | экран (%d, %d)' % (k + 1, o.kind, o.time, s, sx, sy))
    time.sleep(0.45)
    strips.append(grab().crop(STRIP))

# коллаж ленты
w, h = strips[0].size
coll = Image.new('RGB', (w, h * len(strips)))
for i, s in enumerate(strips):
    coll.paste(s, (0, i * h))
coll.save('spike/shots/97_strip.png')
print('коллаж ленты: spike/shots/97_strip.png')

time.sleep(0.3)
print('финал:', idrv.shot('97_final'))
