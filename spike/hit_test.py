"""Точный тест ввода в игровом режиме: мышь и клавиатура поочерёдно.

Задержка старта карты после клика — измерена ~2.4 с (коллаж 23).
Круг №4 карты pearto's Easy: время 3740 мс, osu (235, 380) -> экран (901, 1069).
Слайдер №6: время 4940 мс, osu (210, 167) -> экран (831, 470).
"""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv

hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

idrv.click(957, 470)  # кнопка «Повторить»
t0 = time.perf_counter()
print('t0 — клик «Повторить»')


def wait_until(t: float) -> None:
    while True:
        d = t - (time.perf_counter() - t0)
        if d <= 0:
            return
        time.sleep(min(d, 0.05))


# --- фаза 1: мышь, круг №4 (ожидаемое попадание ~5.6–6.6 с) ---
idrv.move_absolute(901, 1069)
wait_until(5.6)
n1 = 0
while (time.perf_counter() - t0) < 6.6:
    idrv.click(901, 1069, settle=0.0)
    n1 += 1
    time.sleep(0.008)
print('фаза 1 (мышь по кругу): кликов', n1)

# --- фаза 2: клавиша Z, слайдер №6 (~7.0–7.8 с), курсор ставим на его голову ---
idrv.move_absolute(831, 470)
wait_until(6.95)
n2 = 0
while (time.perf_counter() - t0) < 7.8:
    idrv.key(0x5A)  # Z
    n2 += 1
    time.sleep(0.008)
print('фаза 2 (клавиша Z по слайдеру): нажатий', n2)

time.sleep(0.5)
print('снимок:', idrv.shot('25_hit_test'))
