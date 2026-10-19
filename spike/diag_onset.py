"""Диагностика: задержка между появлением HUD и стартом музыки (3 прогона)."""
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


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


hwnd = idrv.find_window()
idrv.activate(hwnd)
ref = load_audio(REF)
rec = BackgroundRecorder(DEV, block_sec=0.05).start()

for run in range(3):
    # старт карты заново (с экрана результатов или паузы)
    img = grab()
    if white(img) < 200:
        idrv.click(1055, 1045)  # Повторить (экран результатов)
        time.sleep(0.5)
        if white(grab()) < 200:
            idrv.key(27)
            time.sleep(1.2)
            idrv.click(960, 535)   # Повторить (пауза)
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

    t_onset = rec.wait_for_onset(timeout=20)
    if t_onset is None:
        print('прогон %d: онсет не найден' % (run + 1))
        continue

    print('прогон %d: HUD +%.3f c от клика | онсет +%.3f c от клика | Δ(HUD→онсет) = %.3f c'
          % (run + 1, t_hud - t_click, t_onset - t_click, t_onset - t_hud))

    # дать карте доиграть немного, затем прервать
    time.sleep(2.0)
    idrv.key(27)
    time.sleep(1.0)

rec.stop()
print('готово')
