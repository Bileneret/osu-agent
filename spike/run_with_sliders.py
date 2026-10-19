"""Прогон карты с ведением слайдеров и спиннерами (полное покрытие).

Фоновый клок (BackgroundRecorder) — первые ноты не пропускаются.
"""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio
from osu_agent.beatmap import Beatmap
from osu_agent.player import MapPlayer
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


hwnd = idrv.find_window()
print('activate:', idrv.activate(hwnd))
time.sleep(0.3)

bm = Beatmap.from_file(OSU_TMP)
ref = load_audio(REF)
player = MapPlayer(bm, ref, 'Speakers (Realtek(R) Audio)', s_offset=0.10)

# фон: рекордер стартует до Play, чтобы не пропустить начало
player.rec.start()

# подготовка: song select -> Play; пауза/результаты -> Повторить; карта идёт -> пауза+Повторить
if white(grab()) > 200:
    idrv.key(27)
    time.sleep(1.2)
    idrv.click(960, 535)
    print('Повторить с паузы (карта шла)')
    time.sleep(0.8)
elif white(grab()) < 200:
    img0 = grab()
    pk = sum(1 for r, g, b in img0.crop((30, 1000, 360, 1080)).getdata() if r > 180 and g < 90 and b > 100)
    if pk > 5000:
        idrv.click(1810, 1005)
        print('Play из song select')
    else:
        # экран результатов: зелёная кнопка «Повторить» внизу по центру
        idrv.click(1055, 1045)
        print('Повторить с экрана результатов')
        time.sleep(2.0)
        if white(grab()) < 200:
            idrv.click(960, 535)
            print('Повторить с паузы (fallback)')
    time.sleep(0.8)

t0 = time.perf_counter()
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('карта идёт (%.2f c)' % (time.perf_counter() - t0))
        break
    time.sleep(0.05)
else:
    print('карта не стартовала')
    player.stop()
    sys.exit(2)

time.sleep(1.5)  # музыка пошла

pos, score = player.calibrate_position()
print('локация: позиция %.3f c | score=%.3f' % (player.t_end_pos, score))

stats = player.play(verbose=True)
print('исполнено:', stats)

# ждём конец карты
last = max((o.end_time or o.time) for o in bm.hit_objects)
wait_until = player.wall_time(last) + 12
while time.perf_counter() < wait_until:
    time.sleep(0.5)

player.stop()
img = grab()
img.save('spike/shots/107_results_sliders.png')
img.resize((880, 495)).save('spike/shots/107_s.png')
print('экран результатов сохранён')
