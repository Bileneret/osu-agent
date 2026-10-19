"""Запускает карту и снимает серию кадров для измерения задержки старта."""
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv

hwnd = idrv.find_window()
print('окно:', hwnd, '| активировано:', idrv.activate(hwnd))

# кнопка Play (большая кнопка внизу справа)
idrv.click(1810, 1005)
t0 = time.perf_counter()
print('клик Play в t=0')

shots = []
for i in range(10):
    time.sleep(max(0.0, 0.5 * i - (time.perf_counter() - t0)))
    p = idrv.shot('seq_%02d' % i)
    shots.append((time.perf_counter() - t0, str(p)))
    print('  кадр %d: t=%.2f c' % (i, shots[-1][0]))

# коллаж 5x2
from PIL import Image
imgs = [Image.open(p).resize((480, 270)) for _, p in shots]
coll = Image.new('RGB', (480 * 5, 270 * 2))
for idx, im in enumerate(imgs):
    coll.paste(im, ((idx % 5) * 480, (idx // 5) * 270))
coll.save('spike/shots/23_collage.png')
print('коллаж: spike/shots/23_collage.png')
