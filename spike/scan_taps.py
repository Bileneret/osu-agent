"""Сканирующая калибровка: тапы по нотам с разными предположениями сдвига S.

Время карты C = позиция_mp3 + S. Тапаем, когда C = T_note, то есть
в момент, когда позиция mp3 = T_note - S. Перебираем S по нотам.
Попадание (hit 300/100/50) одновременно доказывает: тапы Z доходят до геймплея
и калибрует S.
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


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


BOX_BACK = (30, 1000, 360, 1080)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


def to_screen(x, y):
    return idrv.osu_to_screen(x, y)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))

if white(grab()) < 200:
    print('не в игре — готовлю запуск карты')
    for _ in range(5):
        img = grab()
        if pink(img) > 5000:
            print('  в меню')
            break
        idrv.key(27)
        time.sleep(1.5)
    idrv.activate(hwnd)
    time.sleep(0.3)
    idrv.click(1810, 1005)  # Play
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 25:
        if white(grab()) > 200:
            print('  карта стартовала на %.2f c' % (time.perf_counter() - t0))
            break
        time.sleep(0.05)
    else:
        print('  карта не стартовала — стоп')
        idrv.shot('48_stuck')
        sys.exit(2)
    time.sleep(5.0)  # дать музыке пойти

if white(grab()) < 200:
    print('не в игре — стоп')
    sys.exit(1)

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)

# все объекты по времени — чтобы знать зазоры
objs = sorted(bm.hit_objects, key=lambda o: o.time)
circles = [o for o in objs if o.is_circle]

# отбираем круги с зазором >1.2 c от соседей справа и слева
candidates = []
for i, o in enumerate(circles):
    prev_t = max((x.time for x in objs if x.time < o.time), default=-9999)
    next_t = min((x.time for x in objs if x.time > o.time), default=99999)
    if o.time - prev_t > 1200 and next_t - o.time > 1200:
        candidates.append(o)

print('кандидатов с зазором >1.2 c:', len(candidates))

# локация музыки
rec = record_loopback('Speakers (Realtek(R) Audio)', 3.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

S_LIST = [1.0, 0.5, 1.4, 0.7, 1.2, 0.3, 1.6]

# берём кандидатов, у которых время карты заметно впереди
plan = []
for s in S_LIST:
    for o in candidates:
        t_tap = t_ref + (o.time / 1000.0 - s - m.position_sec)
        if t_tap > time.perf_counter() + 0.9:
            plan.append((o, s, t_tap))
            break

print('план тапов:')
for o, s, t in plan[:7]:
    print('  нота %.0f мс | S=%.2f | через %.2f c' % (o.time, s, t - time.perf_counter()))

for o, s, t_tap in plan[:7]:
    while time.perf_counter() < t_tap - 0.9:
        time.sleep(0.05)
    sx, sy = to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap - 0.004:
        pass
    idrv.key(0x5A)
    print('тап: нота %.0f мс, S=%.2f (задержка исполнения %.0f мс)'
          % (o.time, s, (time.perf_counter() - t_tap) * 1000))
    time.sleep(0.25)

time.sleep(0.5)
print('снимок:', idrv.shot('48_scan_taps'))
