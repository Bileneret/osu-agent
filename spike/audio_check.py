"""Проверка аудио-клока: запускаем карту и слушаем loopback обоих устройств.

Realtek (WASAPI idx 15) и JBL BT (idx 16): пишем по 2 с, считаем RMS.
"""
import io
import sys
import time

sys.path.insert(0, r'.')
import numpy as np
import sounddevice as sd
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

for _ in range(4):
    if pink(grab()) > 5000:
        print('в меню')
        break
    idrv.key(27)
    time.sleep(1.5)

idrv.click(1810, 1005)
t0 = time.perf_counter()
print('Play')

# ждём геймплей
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('геймплей на %.2f c' % (time.perf_counter() - t0))
        break
    time.sleep(0.06)

time.sleep(1.0)  # чтобы музыка точно шла


def record_loopback(device_idx: int, seconds: float = 2.0):
    try:
        settings = sd.WasapiSettings(loopback=True)
    except TypeError:
        settings = None
    try:
        rec = sd.rec(int(seconds * 48000), samplerate=48000, channels=2,
                     device=device_idx, extra_settings=settings)
        sd.wait()
        rms = float(np.sqrt(np.mean(rec ** 2)))
        peak = float(np.max(np.abs(rec)))
        return rms, peak
    except Exception as e:
        return None, str(e)


for idx, name in [(15, 'Realtek (WASAPI)'), (16, 'JBL BT (WASAPI)')]:
    rms, peak = record_loopback(idx)
    if rms is None:
        print('%-18s ошибка: %s' % (name, peak))
    else:
        print('%-18s RMS=%.5f  peak=%.4f  %s' % (name, rms, peak, '(тишина)' if peak < 0.001 else '(есть сигнал!)'))
