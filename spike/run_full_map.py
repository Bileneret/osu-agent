"""Финальный прогон: тапы по ВСЕМ нотам карты, дождаться конца, снять результаты.

NF включён — карта не провалится. Исправленные координаты, tap() с KeyDown,
timeBeginPeriod(1). S = 0.10 (по калибровке).
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
S_FIXED = 0.10
SPINNER_VK = None


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

# подготовка: song select -> Play; пауза -> Повторить
if white(grab()) < 200:
    img0 = grab()
    pk = sum(1 for r, g, b in img0.crop((30, 1000, 360, 1080)).getdata() if r > 180 and g < 90 and b > 100)
    if pk > 5000:
        idrv.click(1810, 1005)
        print('Play из song select')
    else:
        idrv.click(960, 535)
        print('Повторить с паузы')
    time.sleep(1.0)

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
    if t_tap < now + 0.8:
        continue
    plan.append((o, t_tap))

print('план: %d объектов (до конца карты)' % len(plan))
n_done = 0
late = 0
for o, t_tap in plan:
    wait = t_tap - 0.35
    nw = time.perf_counter()
    if wait > nw:
        time.sleep(wait - nw)
    sx, sy = idrv.osu_to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap:
        pass
    if o.kind == 'spinner':
        # спиннер: коротко вращаем мышью (не тап)
        for ang in range(0, 720, 45):
            import math
            r = 80
            idrv.move_absolute(int(sx + r * math.cos(math.radians(ang))),
                               int(sy + r * math.sin(math.radians(ang))))
        idrv.move_absolute(sx, sy)
    else:
        idrv.tap(0x5A)
    d = (time.perf_counter() - t_tap) * 1000
    if d > 8:
        late += 1
    n_done += 1
    if n_done % 25 == 0:
        print('  ... %d/%d (поздних %d)' % (n_done, len(plan), late))

print('всего тапов: %d | поздних (>8 мс): %d' % (n_done, late))
print('ожидаю конец карты...')
# ждём завершения: последняя нота + ~12 с
last_t = plan[-1][1] if plan else time.perf_counter()
while time.perf_counter() < last_t + 14:
    time.sleep(0.5)

img = grab()
img.save('spike/shots/106_results_full.png')
img.resize((880, 495)).save('spike/shots/106_s.png')
print('экран результатов сохранён')
