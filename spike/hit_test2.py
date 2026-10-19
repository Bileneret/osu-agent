"""Проверка ввода в геймплее: клавиша Z по кругу №4, затем мышь по кругу №5.

Запуск через кнопку Play (задержка старта измерена ~2.4 с).
Ноты pearto's Easy: №4 — 3740 мс (235,380)->(901,1069); №5 — 4140 мс (158,336)->(684,945).
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


def wait_until(t: float) -> None:
    while True:
        d = t - (time.perf_counter() - t0)
        if d <= 0:
            return
        time.sleep(min(d, 0.05))


# --- фаза A: клавиша Z по кругу №4 (окно ~5.9–6.4 c) ---
idrv.move_absolute(901, 1069)
wait_until(5.5)
na = 0
while (time.perf_counter() - t0) < 6.5:
    idrv.key(0x5A)
    na += 1
    time.sleep(0.008)
print('фаза A: нажатий Z', na)

# --- фаза B: клики мыши по кругу №5 (окно ~6.3–6.9 c) ---
idrv.move_absolute(684, 945)
wait_until(6.55)
nb = 0
while (time.perf_counter() - t0) < 7.2:
    idrv.click(684, 945, settle=0.0)
    nb += 1
    time.sleep(0.008)
print('фаза B: кликов мыши', nb)

time.sleep(0.4)
print('снимок:', idrv.shot('27_hit_test2'))
