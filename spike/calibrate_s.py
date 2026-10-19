"""День 3, шаг 1: калибровка сдвига S серией одиночных тапов.

Каждый тап — по своей ноте, со своим S. После каждого тапа сохраняем кроп HUD
(область точности/разбивки), в конце собираем коллаж — по нему видно, где попадания.

Цель дня: рабочий S -> попадания преимущественно 300.
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
ACC_BOX = (1600, 10, 1920, 115)   # область точности/разбивки
COMBO_BOX = (30, 890, 260, 1000)  # область КОМБО


def grab_full():
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

if white(grab_full()) < 200:
    for _ in range(5):
        if pink(grab_full()) > 5000:
            break
        idrv.key(27)
        time.sleep(1.5)
    idrv.activate(hwnd)
    time.sleep(0.3)
    idrv.click(1810, 1005)  # Play
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 25:
        if white(grab_full()) > 200:
            print('карта стартовала на %.2f c' % (time.perf_counter() - t0))
            break
        time.sleep(0.05)
    else:
        print('карта не стартовала')
        idrv.shot('60_stuck')
        sys.exit(2)
    time.sleep(4.0)

ref = load_audio(REF)
bm = Beatmap.from_file(OSU_TMP)
objs = sorted(bm.hit_objects, key=lambda o: o.time)

rec = record_loopback('Speakers (Realtek(R) Audio)', 4.0)
t_ref = time.perf_counter()
m = locate(ref, rec)
print('музыка на %.3f c | score=%.3f' % (m.position_sec, m.score))

S_LIST = [1.0, 0.8, 1.2, 0.9, 1.1, 0.7, 1.3, 0.85, 1.15, 0.95, 1.05, 1.25]

plan = []
si = 0
now = time.perf_counter()
for o in objs:
    s = S_LIST[si % len(S_LIST)]
    t_tap = t_ref + (o.time / 1000.0 - s - m.position_sec)
    if t_tap < now + 1.0:
        continue
    plan.append((o, s, t_tap))
    si += 1
    if len(plan) >= 12:
        break

print('план из %d тапов' % len(plan))

crops = []
for idx, (o, s, t_tap) in enumerate(plan):
    wait = t_tap - 0.6
    nowp = time.perf_counter()
    if wait > nowp:
        time.sleep(wait - nowp)
    sx, sy = to_screen(o.x, o.y)
    idrv.move_absolute(sx, sy)
    while time.perf_counter() < t_tap - 0.002:
        pass
    idrv.key(0x5A)
    d = (time.perf_counter() - t_tap) * 1000
    time.sleep(0.45)
    crop = grab_full().crop(ACC_BOX)
    crops.append(crop)
    print('  %2d: %s %.0f мс | S=%.2f | исполнено %+.0f мс' % (idx + 1, o.kind, o.time, s, d))

# коллаж кропов
w, h = crops[0].size
coll = Image.new('RGB', (w, h * len(crops)))
for i, c in enumerate(crops):
    coll.paste(c, (0, i * h))
coll = coll.resize((w * 2, h * len(crops) * 2), Image.LANCZOS)
coll.save('spike/shots/60_calib_acc.png')
print('коллаж точности: spike/shots/60_calib_acc.png')
print('снимок:', idrv.shot('60_calib_full'))
