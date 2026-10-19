"""Попытка первого хита: «Повторить» карту и серия кликов по первому кругу.

Координаты первого круга карты pearto's Easy: osu! (235, 380).
Перевод в экран при 1920x1080: scale = 1080/384 = 2.8125, offset_x = 240.
"""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv

hwnd = idrv.find_window()
print('окно игры:', hwnd)
print('активировано:', idrv.activate(hwnd))

# кнопка «Повторить» на экране провала
idrv.click(957, 470)
print('нажал Повторить, жду загрузку...')
time.sleep(1.2)

sx, sy = 901, 1069  # первый круг (235, 380) -> экран
print('долблю по', (sx, sy))
t0 = time.perf_counter()
n = 0
while time.perf_counter() - t0 < 11.0:
    idrv.click(sx, sy, settle=0.0)
    n += 1
    time.sleep(0.012)
print('кликов отправлено:', n)

time.sleep(0.6)
print('снимок:', idrv.shot('21_first_hit_attempt'))
