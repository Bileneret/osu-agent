"""Проверка: проходит ли звук в loopback Realtek при mute, и детект старта музыки.

Запускает карту, пишет loopback Realtek, ищет момент появления звука
(детект старта музыки по RMS в скользящем окне).
"""
import io
import sys
import time

sys.path.insert(0, r'.')
import numpy as np
import soundcard as sc
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


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

# закрыть настройки, если открыты
img = grab()
if white(img) < 200 and pink(img) < 5000:
    idrv.key(27)
    time.sleep(1.0)

# в меню?
for _ in range(4):
    if pink(grab()) > 5000:
        print('в меню')
        break
    idrv.key(27)
    time.sleep(1.5)

mic = sc.get_microphone('Speakers (Realtek(R) Audio)', include_loopback=True)
print('loopback:', mic)

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
print('клик Play')

# пишем loopback 15 секунд в фоне (в отдельном потоке), параллельно детектим геймплей
import threading

recorded = {}


def record():
    recorded['data'] = mic.record(samplerate=48000, numframes=int(48000 * 15))


th = threading.Thread(target=record)
th.start()

# детект геймплея
t_start = None
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        t_start = time.perf_counter()
        break
    time.sleep(0.06)
print('HUD-детект: %s' % ('%.2f c' % (t_start - t0) if t_start else 'нет'))

th.join()
data = recorded['data']
mono = np.abs(data).mean(axis=1)
rms_all = float(np.sqrt(np.mean(data ** 2)))
peak_all = float(np.max(np.abs(data)))
print('запись 15 c: RMS=%.6f peak=%.5f %s' % (rms_all, peak_all, '(ТИШИНА при mute)' if peak_all < 0.0005 else '(СИГНАЛ ЕСТЬ при mute!)'))

# ищем момент старта звука: первое окно 100 мс, где RMS > 0.001
win = 4800  # 100 мс
found = None
for i in range(0, len(mono) - win, win):
    if np.sqrt(np.mean(data[i:i+win] ** 2)) > 0.0015:
        found = i / 48000.0
        break
if found is not None:
    print('звук появился на %.2f c от старта записи (Play+%.2f c)' % (found, found))
else:
    print('звук в записи не детектирован')
