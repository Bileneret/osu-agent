"""Тест клавиши Z в геймплее: выйти в меню, запустить карту, долбить Z по кругу №4.

Окно 5–12 с от клика Play покрывает время ноты 3740 мс при любой наблюдённой
задержке старта (2.4–5.0 с).
"""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv

hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

idrv.key(27)  # Esc — выйти из карты/фейла в меню
time.sleep(1.5)

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
print('t0 — клик Play')

# курсор ставим заранее на круг №4 и долбим Z всё окно
idrv.move_absolute(901, 1069)
n = 0
while (time.perf_counter() - t0) < 12.0:
    idrv.key(0x5A)  # Z
    n += 1
    time.sleep(0.01)
print('нажатий Z:', n, '| t=%.2f' % (time.perf_counter() - t0))

time.sleep(0.4)
print('снимок:', idrv.shot('30_z_test'))
