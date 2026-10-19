"""Вернуться в song select и измерить Δ(HUD→онсет) на трёх запусках карты."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, BackgroundRecorder
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
DEV = 'Speakers (Realtek(R) Audio)'
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


def find_purple(img, y0=500, y1=700):
    crop = img.crop((0, y0, img.width, y1))
    px = crop.load()
    pts = []
    for y in range(0, crop.height, 3):
        for x in range(0, crop.width, 3):
            r, g, b = px[x, y]
            if b > 200 and 90 < r < 170 and g < 90:
                pts.append((x, y + y0))
    if len(pts) < 30:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2


hwnd = idrv.find_window()
idrv.activate(hwnd)
time.sleep(0.3)

# --- выйти в song select при любом состоянии ---
for attempt in range(6):
    img = grab()
    if pink(img) > 5000:
        print('song select OK')
        break
    if white(img) > 200:
        # в игре: пауза -> Повторить? нет: нужен song select: Esc->пауза->Выйти
        idrv.key(27)
        time.sleep(1.2)
        idrv.click(960, 655)  # Выйти (пауза)
        time.sleep(1.5)
        continue
    # главное меню: открыть панель и двойной клик по «играть»
    for step in range(6):
        idrv.move_absolute(700 + step * 60, 600)
        time.sleep(0.04)
    time.sleep(0.3)
    pt = find_purple(grab())
    if pt:
        idrv.move_absolute(*pt)
        time.sleep(0.25)
        idrv.click(*pt)
        time.sleep(0.1)
        idrv.click(*pt)
        print('двойной клик по «играть» в', pt)
        time.sleep(3.0)
    else:
        idrv.key(27)
        time.sleep(1.0)

if pink(grab()) <= 5000:
    print('не удалось выйти в song select')
    idrv.shot('112_stuck')
    sys.exit(1)

# --- измерения Δ ---
ref = load_audio(REF)
rec = BackgroundRecorder(DEV, block_sec=0.05).start()
deltas = []
for run in range(3):
    idrv.click(1810, 1005)  # Play
    t_click = time.perf_counter()
    t_hud = None
    while time.perf_counter() - t_click < 25:
        if white(grab()) > 200:
            t_hud = time.perf_counter()
            break
        time.sleep(0.03)
    if t_hud is None:
        print('прогон %d: HUD не найден' % (run + 1))
        continue
    t_onset = rec.wait_for_onset(timeout=25)
    if t_onset is None:
        print('прогон %d: онсет не найден' % (run + 1))
        continue
    delta = t_onset - t_hud
    deltas.append(delta)
    print('прогон %d: HUD +%.3f c | онсет +%.3f c | Δ(HUD→онсет) = %.3f c'
          % (run + 1, t_hud - t_click, t_onset - t_click, delta))
    # прервать карту и вернуться
    time.sleep(2.0)
    idrv.key(27)
    time.sleep(1.2)
    idrv.click(960, 655)  # Выйти
    time.sleep(2.0)

rec.stop()
if deltas:
    import statistics
    print('Δ: среднее %.3f | разброс %.3f c (%.0f мс)'
          % (statistics.mean(deltas), max(deltas) - min(deltas), (max(deltas) - min(deltas)) * 1000))
