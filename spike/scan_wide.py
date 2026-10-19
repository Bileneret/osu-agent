"""Широкое сканирование S по последовательным нотам.

24 тапа, S от 0.60 до 1.98 с шагом 0.06 — покрывает большой диапазон.
После серии: пауза, снимок статистики, выход — запись покажет точность.
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


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def to_screen(x, y):
    return idrv.osu_to_screen(x, y)


hwnd = idrv.find_window()
idrv.activate(hwnd)

# продолжить, если пауза
if white(grab()) < 200:
    idrv.key(27)  # Esc — продолжить игру (если были на паузе)
    time.sleep(1.5)
    if white(grab()) < 200:
        print('не удалось продолжить игру')
        sys.exit(1)
print('игра идёт')

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
objs = sorted(bm.hit_objects, key=lambda o: o.time)

rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

plan = []
now = time.perf_counter()
i = 0
for o in objs:
    s = 0.60 + 0.06 * i
    if s > 2.0:
        break
    t_tap = t_ref + (o.time / 1000.0 - s - m.position_sec)
    if t_tap < now + 0.9:
        continue
    plan.append((o, s, t_tap))
    i += 1
    if len(plan) >= 24:
        break

print('план: %d тапов, S от %.2f до %.2f' % (len(plan), plan[0][1], plan[-1][1]))

for k, (o, s, t_tap) in enumerate(plan):
    wait = t_tap - 0.6
    nw = time.perf_counter()
    if wait > nw:
        time.sleep(wait - nw)
    sx, sy = to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap - 0.002:
        pass
    idrv.key(0x5A)
    print('  %2d: %s %.0f мс | S=%.2f' % (k + 1, o.kind, o.time, s))
    time.sleep(0.2)

time.sleep(0.5)
print('финальный снимок:', idrv.shot('91_wide_scan'))

# пауза и статистика
idrv.key(27)
time.sleep(1.5)
print('пауза:', idrv.shot('91_pause'))
