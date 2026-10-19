"""День 2: аудио-клок + прицельный тап по ноте.

Шаги: Play -> детект HUD -> запись loopback 4 с -> позиция музыки ->
выбор следующей ноты -> тап Z в её окно -> скриншот.
"""
import io
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, r'.')
import numpy as np
from osu_agent.audio_clock import load_audio, record_loopback, locate, SR
from osu_agent.beatmap import Beatmap
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OSZ = r'./beatmaps/beach_bunny_2602428.osz'
REF = r'./beatmaps/_ref/beach_bunny.mp3'
OSU_TMP = r'./beatmaps/_ref/pearto.osu'

BOX_CROSS = (95, 940, 160, 1010)
BOX_BACK = (30, 1000, 360, 1080)

# подготовка .osu
if not Path(OSU_TMP).exists():
    z = zipfile.ZipFile(OSZ)
    name = [n for n in z.namelist() if 'pearto' in n][0]
    Path(OSU_TMP).write_bytes(z.read(name))
    print('извлечён .osu:', name)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def to_screen(x, y):
    return 240 + x * 2.8125, y * 2.8125


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

# в меню
for _ in range(4):
    if pink(grab()) > 5000:
        break
    idrv.key(27)
    time.sleep(1.5)
print('в меню')

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
circles = [(o.time, o.x, o.y) for o in bm.hit_objects if o.is_circle]
print('карта:', bm.title, '| кругов:', len(circles))

idrv.activate(hwnd)
time.sleep(0.3)
print('foreground перед Play:', idrv.foreground_title())
idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()

# детект HUD
t_hud = None
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        t_hud = time.perf_counter()
        break
    time.sleep(0.05)
if t_hud is None:
    print('карта не стартовала; снимок состояния')
    idrv.shot('40_stuck')
    sys.exit(2)
print('HUD на %.2f c' % (t_hud - t0))

time.sleep(2.5)  # дать музыке пойти

# запись loopback
t_rec_start = time.perf_counter()
rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_rec_end = time.perf_counter()
pos, score = locate(ref, rec)
print('музыка: позиция=%.3f c | score=%.3f | запись %.2f c' % (pos, score, t_rec_end - t_rec_start))

# выбираем ноту: минимум +1.2 с вперёд от конца записи
pos_end = pos  # конец записи соответствует позиции pos в треке
target = None
for t_ms, x, y in circles:
    if t_ms / 1000.0 > pos_end + 1.2:
        target = (t_ms, x, y)
        break
if target is None:
    print('нет подходящей ноты')
    sys.exit(1)

t_ms, x, y = target
sx, sy = to_screen(x, y)
t_tap = t_rec_end + (t_ms / 1000.0 - pos_end)
print('цель: нота на %.0f мс -> экран (%.0f, %.0f) | тап через %.2f c' % (t_ms, sx, sy, t_tap - time.perf_counter()))

idrv.move_absolute(int(sx), int(sy))

# долбим в окне ±0.15 c
while time.perf_counter() < t_tap - 0.15:
    time.sleep(0.003)
n = 0
while time.perf_counter() < t_tap + 0.2:
    idrv.key(0x5A)
    n += 1
    time.sleep(0.006)
print('нажатий Z:', n)

time.sleep(0.4)
print('снимок:', idrv.shot('40_clock_tap'))
