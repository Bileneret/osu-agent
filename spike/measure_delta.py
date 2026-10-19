"""Измерить Δ = T0 − t_click (от клика запуска до старта трека) и её разброс.

T0 определяется корреляцией (locate с hint=0): начало трека в loopback-записи —
единственная зона поиска у нуля, превью карты (100.9 с) в неё не попадает.

Процедура: Play из song select, затем серия «Esc → Повторить».
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


def measure_t0(rec, ref, timeout=25.0):
    """Дождаться старта трека: вернуть (T0, pos, score). T0 = t_end − pos."""
    t_start = time.perf_counter()
    best = None
    while time.perf_counter() - t_start < timeout:
        res = rec.locate(ref, 1.5, hint=0.0)
        if res is not None:
            pos, score, t_end = res
            if best is None or score > best[2]:
                best = (pos, score, t_end)
            if score > 0.5 and -0.5 <= pos <= 4.0:
                return t_end - pos, pos, score
        time.sleep(0.05)
    if best is not None:
        print('  (лучший за попытку: pos=%.3f score=%.2f)' % (best[0], best[1]))
    return None, None, None


def main():
    ref = load_audio(REF)
    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)

    rec = BackgroundRecorder(DEV, block_sec=0.05).start()
    time.sleep(0.6)

    results = []
    for attempt in range(5):
        if attempt == 0:
            kind = 'Play(songselect)'
            idrv.move_absolute(*PLAY_BTN)
            time.sleep(0.06)
            t_click = time.perf_counter()   # KeyDown уходит сразу после этой метки
            idrv.click()
        else:
            kind = 'Retry(pause)'
            idrv.key(27)
            time.sleep(1.0)
            idrv.move_absolute(*PAUSE_RETRY)
            time.sleep(0.06)
            t_click = time.perf_counter()
            idrv.click()

        t0, pos, score = measure_t0(rec, ref)
        if t0 is None:
            print('попытка %d (%s): T0 не найден' % (attempt + 1, kind))
            idrv.shot('121_delta_fail')
            break
        d = t0 - t_click
        results.append(d)
        print('%-18s Δ = %.3f c | pos=%.3f score=%.2f' % (kind, d, pos, score))
        time.sleep(0.4)

    rec.stop()
    if results:
        print('---')
        print('Δ: n=%d среднее %.3f c | разброс %.0f мс | σ=%.0f мс'
              % (len(results), statistics.mean(results),
                 (max(results) - min(results)) * 1000,
                 statistics.pstdev(results) * 1000 if len(results) > 1 else 0.0))
        print('все: ' + ', '.join('%.3f' % r for r in results))


if __name__ == '__main__':
    main()
