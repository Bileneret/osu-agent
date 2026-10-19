"""Измерить Δ = T0 − t_click на серии перезапусков (Retry) и на Play из song select.

T0 считается как t_end − pos по каждой локации (locate с hint=0 покрывает 0..31 с,
поэтому превью на 100.9 с не мешает). Несколько точек внутри попытки дают проверку
согласованности: T0 из разных моментов должны совпасть.
"""
import io
import statistics
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, BackgroundRecorder
from osu_agent import input_driver as idrv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
DEV = 'Speakers (Realtek(R) Audio)'
PLAY_BTN = (1810, 1005)
PAUSE_RETRY = (960, 535)
PAUSE_EXIT = (960, 655)


def run_attempt(rec, ref, t_click, seconds=6.0):
    """Собрать локации за `seconds` после клика. Вернуть список (dt, pos, score)."""
    out = []
    while True:
        dt = time.perf_counter() - t_click
        if dt > seconds:
            break
        res = rec.locate(ref, 1.0, hint=0.0)
        if res is not None:
            pos, score, t_end = res
            out.append((t_end - t_click, pos, score))
    return out


def summarize(attempts):
    print('\n=== итог ===')
    t0s = []
    for i, log in enumerate(attempts, 1):
        good = [(t, p, s) for (t, p, s) in log if s >= 0.25 and -1.0 <= p <= 12.0]
        if not good:
            print('попытка %d: нет надёжных локаций (лучший score %.2f)' %
                  (i, max((s for _, _, s in log), default=0)))
            continue
        est = [t - p for (t, p, s) in good]
        med = statistics.median(est)
        spread = (max(est) - min(est)) * 1000
        t0s.append(med)
        print('попытка %d: локаций %d/%d | T0-t_click = %.3f c | разброс оценок %.0f мс | первый детект +%.2f c (pos=%.2f, score=%.2f)'
              % (i, len(good), len(log), med, spread, good[0][0], good[0][1], good[0][2]))
    if len(t0s) > 1:
        print('Δ по попыткам: %s' % ', '.join('%.3f' % x for x in t0s))
        print('среднее %.3f | разброс %.0f мс | σ=%.0f мс'
              % (statistics.mean(t0s), (max(t0s) - min(t0s)) * 1000,
                 statistics.pstdev(t0s) * 1000))


def main():
    ref = load_audio(REF)
    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)
    rec = BackgroundRecorder(DEV, block_sec=0.05).start()
    time.sleep(0.6)

    attempts = []
    n_retry = 3
    for attempt in range(n_retry + 1):
        if attempt < n_retry:
            idrv.key(27)              # Esc -> пауза
            time.sleep(1.0)
            idrv.move_absolute(*PAUSE_RETRY)
            time.sleep(0.08)
            t_click = time.perf_counter()
            idrv.click()
            kind = 'Retry'
        else:
            idrv.key(27)              # пауза
            time.sleep(1.0)
            idrv.click(*PAUSE_EXIT)   # Выйти -> song select
            time.sleep(2.5)
            idrv.move_absolute(*PLAY_BTN)
            time.sleep(0.08)
            t_click = time.perf_counter()
            idrv.click()
            kind = 'Play'
            idrv.shot('123_after_play')
        log = run_attempt(rec, ref, t_click)
        print('--- %s: %d локаций' % (kind, len(log)))
        for (t, p, s) in log[:14]:
            print('    t_click+%.2f c: pos=%6.2f score=%.3f' % (t, p, s))
        attempts.append(log)
        time.sleep(0.3)

    rec.stop()
    summarize(attempts)


if __name__ == '__main__':
    main()
