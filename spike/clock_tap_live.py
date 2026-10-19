"""Главный тест дня 2: клок на живой карте + тап Z по ноте.

В отличие от clock_tap_test — работает по уже играющей карте:
запись loopback -> позиция музыки -> следующая нота -> тап -> скриншот.
"""
import io
import sys
import time
import zipfile
from pathlib import Path

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
    return 240 + x * 2.8125, y * 2.8125


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
if white(grab()) < 200:
    print('не в игре — стоп')
    sys.exit(1)
print('в игре; записываю звук...')

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
circles = [(o.time, o.x, o.y) for o in bm.hit_objects if o.is_circle]

rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_end = time.perf_counter()
m = locate(ref, rec)
pos, score = m.position_sec, m.score
print('позиция музыки: %.3f c (конец записи) | score=%.3f' % (pos, score))

target = None
for t_ms, x, y in circles:
    if t_ms / 1000.0 > pos + 1.0:
        target = (t_ms, x, y)
        break
if target is None:
    print('нет подходящей ноты')
    sys.exit(1)

t_ms, x, y = target
sx, sy = to_screen(x, y)
t_tap = t_end + (t_ms / 1000.0 - pos)
dt = t_tap - time.perf_counter()
print('цель: нота %.0f мс -> экран (%.0f, %.0f) | тап через %.2f c' % (t_ms, sx, sy, dt))

idrv.move_absolute(int(sx), int(sy))

if dt > 0.2:
    time.sleep(dt - 0.2)
n = 0
t_hold_end = t_tap + 0.25
while time.perf_counter() < t_hold_end:
    idrv.key(0x5A)
    n += 1
    time.sleep(0.006)
print('нажатий Z:', n)

time.sleep(0.35)
print('снимок:', idrv.shot('46_clock_tap_live'))
