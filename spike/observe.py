"""Наблюдение: возобновляется ли загрузка/стартует ли карта (коллаж кадров)."""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

# клик по центру экрана — отдать фокус
idrv.click(960, 540)
t0 = time.perf_counter()

shots = []
for i in range(12):
    time.sleep(max(0.0, 0.5 * i - (time.perf_counter() - t0)))
    p = idrv.shot('obs_%02d' % i)
    shots.append((time.perf_counter() - t0, str(p)))

imgs = [Image.open(p).resize((400, 225)) for _, p in shots]
coll = Image.new('RGB', (400 * 4, 225 * 3))
for idx, im in enumerate(imgs):
    coll.paste(im, ((idx % 4) * 400, (idx // 4) * 225))
coll.save('spike/shots/31_observe.png')
print('коллаж: spike/shots/31_observe.png')
for t, p in shots:
    print('  t=%.2f %s' % (t, p))
