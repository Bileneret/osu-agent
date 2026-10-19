"""Проверка консистентности клока: два замера позиции с интервалом + таймер карты."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, record_loopback, locate
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
BOX_CROSS = (95, 940, 160, 1010)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
state = 'игра' if white(grab()) > 200 else 'не игра'
print('состояние:', state)
if state != 'игра':
    sys.exit(1)

ref = load_audio(REF)

for i in (1, 2):
    t0 = time.perf_counter()
    rec = record_loopback('Speakers (Realtek(R) Audio)', 3.0)
    t_end = time.perf_counter()
    m = locate(ref, rec)
    print('замер %d: позиция конца=%.3f c | score=%.3f | t_end=%.2f' % (i, m.position_sec, m.score, t_end))
    if i == 1:
        scr = grab()
        scr.save('spike/shots/47_during_clock.png')
        time.sleep(4.0)

print('снимок с таймером: spike/shots/47_during_clock.png')
