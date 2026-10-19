"""Контрольный прогон: серия 20 нот подряд с S=0.10 (по итогам калибровки).

Исправленная формула координат (idrv.osu_to_screen), тап через KeyDown,
timeBeginPeriod(1) — всё из input_driver.
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
STRIP = (60, 10, 900, 230)
S_FIXED = 0.10
N_NOTES = 20


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
time.sleep(0.3)

# если на паузе — «Повторить» (вторая кнопка)
if white(grab()) < 200:
    idrv.click(960, 535)
    print('нажал Повторить')
    time.sleep(1.0)
else:
    print('не на паузе?')

t0 = time.perf_counter()
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('карта идёт (%.2f c)' % (time.perf_counter() - t0))
        break
    time.sleep(0.05)
else:
    print('карта не стартовала')
    sys.exit(2)

time.sleep(3.5)

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
objs = sorted(bm.hit_objects, key=lambda o: o.time)

rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

plan = []
now = time.perf_counter()
for o in objs:
    t_tap = t_ref + (o.time / 1000.0 - S_FIXED - m.position_sec)
    if t_tap < now + 1.2:
        continue
    plan.append((o, t_tap))
    if len(plan) >= N_NOTES:
        break

print('серия: %d нот, S=%.2f' % (len(plan), S_FIXED))
strips = []
late = 0
for k, (o, t_tap) in enumerate(plan):
    wait = t_tap - 0.4
    nw = time.perf_counter()
    if wait > nw:
        time.sleep(wait - nw)
    sx, sy = idrv.osu_to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap:
        pass
    idrv.tap(0x5A)
    d = (time.perf_counter() - t_tap) * 1000
    if d > 15:
        late += 1
    print('  %2d: %s %6.0f мс | (%4d,%4d) | исполнено %+.0f мс' % (k + 1, o.kind, o.time, sx, sy, d))
    time.sleep(0.35)
    strips.append(grab().crop(STRIP))

w, h = strips[0].size
coll = Image.new('RGB', (w, h * len(strips)))
for i, s in enumerate(strips):
    coll.paste(s, (0, i * h))
coll.save('spike/shots/102_series_strip.png')
print('поздних тапов (>15 мс):', late)
print('коллаж: spike/shots/102_series_strip.png')

time.sleep(0.3)
idrv.key(27)  # пауза
time.sleep(1.5)
img = grab()
img.crop((550, 800, 1400, 960)).resize((1700, 320)).save('spike/shots/102_stats.png')
img.resize((880, 495)).save('spike/shots/102_pause.png')
print('статистика сохранена')
