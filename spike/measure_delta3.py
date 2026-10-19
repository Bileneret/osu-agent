"""Точная калибровка Δ (T0 − t_click) через сэмпл-точный детект онсета.

Детект: `wait_for_onset` (тишина → скачок громкости). T0 = t_onset − ref_onset,
где ref_onset — первое звучание в эталонном треке (секунды). Проверяем разброс
по серии перезапусков: если σ мала, первую ноту (140 мс) можно бить по предсказанию.
"""
import io
import statistics
import sys
import time

sys.path.insert(0, r'.')
from osu_agent.audio_clock import load_audio, BackgroundRecorder, first_sound_time
from osu_agent import input_driver as idrv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REF = r'./beatmaps/_ref/beach_bunny.mp3'
DEV = 'Speakers (Realtek(R) Audio)'
PAUSE_RETRY = (960, 535)


def main():
    ref = load_audio(REF)
    ref_onset = first_sound_time(ref)
    print('ref_onset = %.3f c' % ref_onset)
    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)
    rec = BackgroundRecorder(DEV, block_sec=0.05).start()
    time.sleep(0.6)

    results = []
    for attempt in range(5):
        idrv.key(27)
        time.sleep(1.0)
        idrv.move_absolute(*PAUSE_RETRY)
        time.sleep(0.08)
        t_click = time.perf_counter()
        idrv.click()

        t_onset = rec.wait_for_onset(threshold=0.02, silence=0.3, timeout=10.0, poll=0.02)
        if t_onset is None:
            print('попытка %d: онсет не найден' % (attempt + 1))
            idrv.shot('124_onset_fail')
            continue
        delta = (t_onset - ref_onset) - t_click
        results.append(delta)
        # проверка корреляцией: ожидаем позицию ~ (сейчас − T0)
        time.sleep(0.9)
        res = rec.locate(ref, 1.0, hint=1.0)
        chk = ''
        if res:
            pos, score, t_end = res
            t0_corr = (t_end - pos) - t_click
            chk = ' | corr: T0-t_click=%.3f (pos=%.2f score=%.2f, Δ=%.3f)' % (t0_corr, pos, score, t0_corr - delta)
        print('попытка %d: онсет t_click+%.3f | T0-t_click = %.3f c%s' % (attempt + 1, t_onset - t_click, delta, chk))
        time.sleep(0.3)

    rec.stop()
    if results:
        print('---')
        print('Δ(RMS): n=%d среднее %.3f | разброс %.0f мс | σ=%.0f мс'
              % (len(results), statistics.mean(results),
                 (max(results) - min(results)) * 1000,
                 statistics.pstdev(results) * 1000))
        print('все: ' + ', '.join('%.3f' % r for r in results))


if __name__ == '__main__':
    main()
