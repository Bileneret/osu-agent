"""Диагностика: что слышно в паузе и сразу после клика «Повторить».

Печатает профиль RMS (по 100 мс) — видно, есть ли звук интерфейса от клика,
когда начинается интро и когда стартует музыка карты.
"""
import sys
import time

sys.path.insert(0, r'.')
sys.path.insert(0, r'./spike')
import numpy as np
from osu_agent import input_driver as idrv
import run_ss as R
from osu_agent.audio_clock import BackgroundRecorder


def rms_of(rec, seconds=0.25):
    audio, t_end = rec.recent(seconds)
    if audio is None or len(audio) < 4800:
        return -1.0
    return float(np.sqrt(np.mean(audio[-4800:] ** 2)))


def main():
    idrv.activate(idrv.find_window())
    time.sleep(0.3)
    rec = BackgroundRecorder(R.DEV, block_sec=0.05).start()
    time.sleep(0.8)

    if not R.ensure_pause():
        sys.exit(2)

    print('--- профиль в паузе (2 с) ---')
    for i in range(20):
        print('  %5.2f c: RMS=%.4f %s' % (i * 0.1, rms_of(rec), '#' * int(rms_of(rec) * 200)))
        time.sleep(0.1)

    print('--- клик «Повторить» и 7 с после ---')
    idrv.move_absolute(*R.PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    while True:
        dt = time.perf_counter() - t_click
        if dt > 7.0:
            break
        r = rms_of(rec)
        print('  %5.2f c: RMS=%.4f %s' % (dt, r, '#' * int(r * 200)))
        time.sleep(0.1)

    print('--- контрольный wait_for_onset (earliest = t_click+1.0) ---')
    rec.stop()
    from osu_agent.audio_clock import load_audio, first_sound_time
    ref_onset = first_sound_time(load_audio(R.REF))
    rec2 = BackgroundRecorder(R.DEV, block_sec=0.05).start()
    time.sleep(0.3)
    idrv.key(27)
    time.sleep(1.2)
    idrv.move_absolute(*R.PAUSE_RETRY)
    time.sleep(0.08)
    t_click2 = time.perf_counter()
    idrv.click()
    t_onset = rec2.wait_for_onset(timeout=8.0, poll=0.02, earliest=t_click2 + 1.0)
    if t_onset is None:
        print('  онсет: не найден')
    else:
        print('  онсет: +%.3f c после клика | Δ(T0−t_click) = %.3f c (ref_onset=%.3f)'
              % (t_onset - t_click2, t_onset - ref_onset - t_click2, ref_onset))
    rec2.stop()


if __name__ == '__main__':
    main()
