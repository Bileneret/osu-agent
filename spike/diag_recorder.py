"""Диагностика: сверка фонового рекордера и блокирующей записи на одном моменте."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, locate, record_loopback, BackgroundRecorder
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
DEV = 'Speakers (Realtek(R) Audio)'
BOX_CROSS = (95, 940, 160, 1010)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


hwnd = idrv.find_window()
idrv.activate(hwnd)
time.sleep(0.3)

# подготовка карты
if white(grab()) < 200:
    img0 = grab()
    pk = sum(1 for r, g, b in img0.crop((30, 1000, 360, 1080)).getdata() if r > 180 and g < 90 and b > 100)
    if pk > 5000:
        idrv.click(1810, 1005)
        print('Play')
    else:
        idrv.click(1055, 1045)
        print('Повторить с результатов')
        time.sleep(2.0)
        if white(grab()) < 200:
            idrv.click(960, 535)
            print('Повторить с паузы')
    time.sleep(0.8)

t0 = time.perf_counter()
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('карта идёт')
        break
    time.sleep(0.05)

time.sleep(4.0)

ref = load_audio(REF)
rec = BackgroundRecorder(DEV).start()
time.sleep(3.0)

r_bg = rec.locate(ref, 2.5)
if r_bg is None:
    print('фоновый рекордер: локация не удалась')
    sys.exit(1)
pos_bg, score_bg, t_end_bg = r_bg
print('фоновый:    pos=%.3f | score=%.3f | t_end=%.3f' % (pos_bg, score_bg, t_end_bg))

t_start = time.perf_counter()
audio = record_loopback(DEV, 3.0)
t_stop = time.perf_counter()
m_bl = locate(ref, audio)
pos_bl, score_bl = m_bl.position_sec, m_bl.score
print('блокирующий: pos=%.3f | score=%.3f | t_stop=%.3f' % (pos_bl, score_bl, t_stop))

# ожидание: pos_bl - pos_bg ≈ t_stop - t_end_bg
d_pos = pos_bl - pos_bg
d_time = t_stop - t_end_bg
print()
print('Δ позиции (блок - фон): %.3f c' % d_pos)
print('Δ времени (t_stop - t_end_bg): %.3f c' % d_time)
print('РАСХОЖДЕНИЕ: %.3f c (%.0f мс) — должно быть ~0' % (d_pos - d_time, (d_pos - d_time) * 1000))

# и таймер карты на экране — для контроля глазами
img = grab()
img.save('spike/shots/109_timer.png')
img.crop((40, 990, 400, 1060)).resize((720, 140)).save('spike/shots/109_timer_crop.png')
rec.stop()
print('снимок таймера сохранён')
