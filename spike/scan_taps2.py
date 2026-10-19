"""Сканирующие тапы: по одному тапу на каждый объект карты, разные гипотезы S.

Цель: получить ХОТЬ ОДНО попадание (hit 300/100/50) — это докажет, что тапы Z
доходят до геймплея, и даст оценку сдвига S (время карты = позиция mp3 + S).
"""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, record_loopback, locate
from osu_agent.beatmap import Beatmap
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
OSU_TMP = r'./beatmaps/_ref/pearto.osu'
BOX_CROSS = (95, 940, 160, 1010)
BOX_BACK = (30, 1000, 360, 1080)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


def to_screen(x, y):
    return idrv.osu_to_screen(x, y)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

if white(grab()) < 200:
    for _ in range(5):
        if pink(grab()) > 5000:
            break
        idrv.key(27)
        time.sleep(1.5)
    idrv.activate(hwnd)
    time.sleep(0.3)
    idrv.click(1810, 1005)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 25:
        if white(grab()) > 200:
            print('карта стартовала на %.2f c' % (time.perf_counter() - t0))
            break
        time.sleep(0.05)
    else:
        print('карта не стартовала')
        sys.exit(2)
    time.sleep(5.0)

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
objs = sorted(bm.hit_objects, key=lambda o: o.time)
print('объектов в карте:', len(objs))

rec = record_loopback('Speakers (Realtek(R) Audio)', 3.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

S_LIST = [1.0, 0.5, 1.4, 0.7, 1.2, 0.3, 1.6, 0.0, 1.8, 0.9]

# выбираем объекты впереди: время карты > (M + 1.2 c + S)
plan = []
si = 0
for o in objs:
    t_needed = o.time / 1000.0 - m.position_sec  # сколько секунд ждать (если S=0)
    if t_needed < 1.2:
        continue
    s = S_LIST[si % len(S_LIST)]
    si += 1
    t_tap = t_ref + (o.time / 1000.0 - s - m.position_sec)
    if t_tap < time.perf_counter() + 0.5:
        continue
    plan.append((o, s, t_tap))
    if len(plan) >= 10:
        break

print('план (%d тапов):' % len(plan))
for o, s, t in plan:
    print('  %s %.0f мс | S=%.1f | +%.2f c' % (o.kind, o.time, s, t - time.perf_counter()))

for o, s, t_tap in plan:
    wait = t_tap - 0.7
    now = time.perf_counter()
    if wait > now:
        time.sleep(wait - now)
    sx, sy = to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap - 0.004:
        pass
    idrv.key(0x5A)
    print('  тап %s %.0f мс, S=%.1f | исполнено %+.0f мс' %
          (o.kind, o.time, s, (time.perf_counter() - t_tap) * 1000))

time.sleep(0.5)
print('снимок:', idrv.shot('49_scan2'))
