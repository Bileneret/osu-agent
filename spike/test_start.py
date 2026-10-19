"""Быстрый тест предсказанного старта: калибровка Δ + первые 3 с карты.

После прогона ставим паузу и снимаем скриншот: на паузе видно «Точность» текущей
попытки — 100.00% означает, что первый слайдер (140 мс) взят с 300.
"""
import io
import statistics
import sys
import time

sys.path.insert(0, r'.')
sys.path.insert(0, r'./spike')
import run_ss as R
from osu_agent.audio_clock import load_audio
from osu_agent.beatmap import Beatmap
from osu_agent.player import MapPlayer
from osu_agent import input_driver as idrv


def main():
    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)
    bm = Beatmap.from_file(R.OSU_TMP)
    ref = load_audio(R.REF)
    player = MapPlayer(bm, ref, R.DEV, s_offset=0.10)
    player.rec.start()
    time.sleep(0.5)

    if not R.ensure_pause():
        player.stop()
        sys.exit(2)

    deltas = []
    for _ in range(2):
        d = R.calibrate_once(player)
        if d is not None:
            deltas.append(d)
        if not R.ensure_pause():
            player.stop()
            sys.exit(2)
    if not deltas:
        print('калибровка не удалась')
        player.stop()
        sys.exit(3)
    delta = statistics.mean(deltas)
    print('Δ = %.3f c (замеры: %s)' % (delta, ', '.join('%.3f' % d for d in deltas)))

    # тестовый запуск: играем первые 3 с, затем пауза
    idrv.move_absolute(*R.PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    player.predicted_start(t_click, delta)
    player.start_onset_watcher(not_before=t_click + 2.0, timeout=6.0)
    t0_pred = t_click + delta
    print('T0 ожидается в +%.3f c; тап первой ноты в +%.3f c' % (delta, delta + 0.04))
    stats = player.play(until_time_ms=600, verbose=False)
    print('исполнено: %s' % stats)
    idrv.key(27)          # сразу пауза, чтобы второй объект (940 мс) не ушёл
    time.sleep(1.5)
    idrv.shot('128_test_first')
    print('скриншот: spike/shots/128_test_first.png')
    print('ожидание: точность 100.00%, прогресс 1%')
    player.stop()


if __name__ == '__main__':
    main()
