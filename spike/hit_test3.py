"""Решающий тест ввода в геймплее: непрерывная долбёжка с самого старта карты.

Фаза Z  : 0.0–4.6 c, курсор на слайдере №1 (140 мс)  -> экран (307, 942)
Фаза мышь: 4.5–11.0 c, курсор на круге №4 (3740 мс)  -> экран (901, 1069)

При любой задержке старта в диапазоне 2.4–4.5 с обе ноты попадают в свои фазы.
"""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv

hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

idrv.click(1810, 1005)  # Play
t0 = time.perf_counter()
print('t0 — клик Play')

# --- фаза Z: слайдер №1 ---
idrv.move_absolute(307, 942)
ns = 0
while (time.perf_counter() - t0) < 4.6:
    idrv.key(0x5A)  # Z
    ns += 1
print('фаза Z: нажатий', ns, '| t=%.2f' % (time.perf_counter() - t0))

# --- фаза мышь: круг №4 ---
idrv.move_absolute(901, 1069)
nm = 0
while (time.perf_counter() - t0) < 11.0:
    idrv.click(901, 1069, settle=0.0)
    nm += 1
    time.sleep(0.006)
print('фаза мышь: кликов', nm, '| t=%.2f' % (time.perf_counter() - t0))

time.sleep(0.4)
print('снимок:', idrv.shot('29_final_hit_test'))
