"""Замер джиттера планировщика: timeBeginPeriod(1) + спин-ожидание.

Схема: сон до (цель - 1 мс), затем активное ожидание; измеряем отклонение
фактического момента от цели. Цель — медиана < 1 мс, p95 < 3 мс (жёсткая цель p95 < 1 мс).
"""
import ctypes
import io
import sys
import time

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

winmm = ctypes.windll.winmm
winmm.timeBeginPeriod(1)

N = 500
PERIOD = 0.010  # 10 мс между событиями

errors_us = []
t0 = time.perf_counter()
for k in range(1, N + 1):
    target = t0 + k * PERIOD
    # сон до цели минус 1.2 мс, потом спин
    while True:
        remaining = target - time.perf_counter() - 0.0012
        if remaining <= 0:
            break
        time.sleep(max(0.0, remaining))
    while time.perf_counter() < target:
        pass
    err = (time.perf_counter() - target) * 1e6
    errors_us.append(err)

winmm.timeEndPeriod(1)

arr = np.array(errors_us)
print('замеров: %d, интервал %.0f мс' % (N, PERIOD * 1000))
print('ошибка планировщика (мкс):')
print('  медиана:  %+8.1f' % np.median(arr))
print('  среднее:  %+8.1f' % arr.mean())
print('  |ошибка| медиана: %8.1f' % np.median(np.abs(arr)))
print('  p95 |ошибка|: %8.1f' % np.percentile(np.abs(arr), 95))
print('  p99 |ошибка|: %8.1f' % np.percentile(np.abs(arr), 99))
print('  максимум: %8.1f' % np.max(np.abs(arr)))

ok_median = np.median(np.abs(arr)) < 1000
ok_p95 = np.percentile(np.abs(arr), 95) < 3000
print()
print('критерий дня 2 (медиана < 1 мс, p95 < 3 мс):', 'ВЫПОЛНЕН' if (ok_median and ok_p95) else 'НЕ выполнен')
