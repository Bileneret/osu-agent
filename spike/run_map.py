"""Прогон карты: адаптивный старт, полное покрытие, скриншот результата.

    python spike/run_map.py --osu <карта.osu> --audio <трек.mp3> [--device NAME]
                            [--delta SEC] [--test] [--search TEXT] [--shot PREFIX]

Адаптивный старт (решение принимается по самой карте):
  * первая нота >= 1.5 с — карта стартует напрямую: ждём фактический первый звук
    и привязываемся к нему (калибровка Δ не нужна, детект успевает задолго до ноты);
  * первая нота < 1.5 с — предсказанный старт: калибровка Δ (клик «Повторить» →
    старт трека), привязка по предсказанию, затем фактический онсет уточняет якорь
    для всех последующих объектов. Так закрывается нота, звучащая раньше, чем
    звук вообще становится доступен детектору.

Состояние игры приводится автоматически: song select / пауза / экран результатов
распознаются по цвету и доводятся до паузы (бой всегда стартует из паузы).
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from osu_agent import input_driver as idrv
from osu_agent.audio_clock import first_sound_time, load_audio
from osu_agent.beatmap import Beatmap
from osu_agent.player import MapPlayer

PLAY_BTN = (1810, 1005)
PAUSE_RETRY = (960, 535)
PAUSE_EXIT = (960, 655)
RESULTS_BACK = (110, 1048)     # центр розовой «Назад» на экране результатов
SEARCH_BOX = (1560, 115)       # поле «найти...» в song select

EARLIEST_MARGIN = 0.55         # раньше этого после клика онсетов быть не может
DELTA_RANGE = (1.5, 8.0)       # допустимый диапазон Δ (загрузка + интро)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def count(img, box, pred):
    return sum(1 for r, g, b in img.crop(box).getdata() if pred(r, g, b))


def is_songselect(img):
    return count(img, (30, 1000, 360, 1080), lambda r, g, b: r > 180 and g < 90 and b > 100) > 5000


def is_pause(img):
    green = count(img, (300, 370, 1620, 470), lambda r, g, b: g > 150 and r < 200 and b < 90)
    return green > 50000


def is_playing(img):
    return count(img, (95, 940, 160, 1010), lambda r, g, b: r > 190 and g > 190 and b > 190) > 200


def ensure_pause(verbose=True, tries=8):
    """Привести игру к экрану паузы (возврат True при успехе)."""
    for _ in range(tries):
        img = grab()
        if is_pause(img):
            if verbose:
                print('  состояние: пауза')
            return True
        if is_playing(img):
            if verbose:
                print('  состояние: игра -> Esc')
            idrv.key(27)
            time.sleep(1.4)
            continue
        if is_songselect(img):
            if verbose:
                print('  состояние: song select -> Play')
            idrv.click(*PLAY_BTN)
            time.sleep(4.5)
            idrv.key(27)
            time.sleep(1.4)
            continue
        if verbose:
            print('  состояние: результаты -> Назад')
        idrv.click(*RESULTS_BACK)
        time.sleep(2.5)
    print('  НЕ удалось выйти в паузу')
    return False


def ensure_songselect(verbose=True, tries=6):
    """Привести игру к song select (нужно для выбора карты по --search)."""
    for _ in range(tries):
        img = grab()
        if is_songselect(img):
            return True
        if is_pause(img):
            idrv.click(*PAUSE_EXIT)
            time.sleep(2.2)
            continue
        if is_playing(img):
            idrv.key(27)
            time.sleep(1.4)
            continue
        idrv.click(*RESULTS_BACK)
        time.sleep(2.5)
    return False


def search_in_songselect(text: str) -> None:
    """Ввести строку в поле поиска song select (заменяя прежний запрос)."""
    idrv.click(*SEARCH_BOX)
    time.sleep(0.4)
    idrv.key_down(idrv.VK_CTRL)
    idrv.key(idrv.VK_A)
    time.sleep(0.06)
    idrv.key_up(idrv.VK_CTRL)
    time.sleep(0.25)
    idrv.type_text(text)
    time.sleep(1.2)


def calibrate_once(player: MapPlayer, timeout=8.0):
    """Клик «Повторить» -> замер T0 − t_click по онсету (выбросы отбрасываются)."""
    idrv.move_absolute(*PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    t_onset = player.rec.wait_for_onset(timeout=timeout, poll=0.02,
                                        earliest=t_click + EARLIEST_MARGIN)
    if t_onset is None:
        print('  калибровка: онсет не найден')
        return None
    delta = (t_onset - player.ref_onset) - t_click
    if not (DELTA_RANGE[0] <= delta <= DELTA_RANGE[1]):
        print('  калибровка: Δ = %.3f c — выброс, отброшен' % delta)
        return None
    print('  калибровка: Δ = %.3f c' % delta)
    return delta


def calibrate_delta(player: MapPlayer) -> float:
    """Два согласованных замера Δ (до 5 попыток). Возврат None — не удалось."""
    deltas: list[float] = []
    for _ in range(5):
        if len(deltas) >= 2 and (max(deltas) - min(deltas)) <= 0.06:
            break
        d = calibrate_once(player)
        if d is not None:
            deltas.append(d)
        if not ensure_pause():
            return None  # type: ignore[return-value]
    if len(deltas) < 2:
        print('калибровка не удалась (нет двух валидных замеров)')
        return None  # type: ignore[return-value]
    spread = max(deltas) - min(deltas)
    if spread > 0.08:
        print('калибровка нестабильна: разброс %.0f мс' % (spread * 1000))
        return None  # type: ignore[return-value]
    delta = statistics.mean(deltas)
    print('Δ = %.3f c (замеры: %s)' % (delta, ', '.join('%.3f' % d for d in deltas)))
    return delta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Прогон карты osu! внешним агентом')
    ap.add_argument('--osu', required=True, help='путь к файлу карты .osu')
    ap.add_argument('--audio', required=True, help='путь к аудиофайлу карты (mp3/ogg)')
    ap.add_argument('--device', default='Speakers (Realtek(R) Audio)',
                    help='устройство вывода для loopback-захвата')
    ap.add_argument('--s-offset', type=float, default=0.10,
                    help='компенсация S: аудио-латентность + ввод (сек)')
    ap.add_argument('--delta', type=float, default=None,
                    help='задать Δ вручную (иначе калибровка)')
    ap.add_argument('--search', default=None,
                    help='строка для поиска карты в song select перед прогоном')
    ap.add_argument('--test', action='store_true',
                    help='быстрый тест: сыграть только первый объект и снять паузу')
    ap.add_argument('--shot', default='spike/shots/run_map',
                    help='префикс имён скриншотов')
    ap.add_argument('--cpu', type=int, default=None,
                    help='привязать главный поток к логическому ядру (например, последнее)')
    args = ap.parse_args(argv)

    if args.cpu is not None:
        import os
        core = args.cpu if args.cpu >= 0 else max(0, (os.cpu_count() or 2) - 1)
        print('affinity:', idrv.set_cpu_affinity(core), '(ядро %d из %d)'
              % (core, os.cpu_count() or 0))

    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)

    bm = Beatmap.from_file(args.osu)
    ref = load_audio(args.audio)
    ref_onset = first_sound_time(ref)
    first_note = min(o.time for o in bm.hit_objects) / 1000.0
    player = MapPlayer(bm, ref, args.device, s_offset=args.s_offset)
    player.rec.start()   # захват звука должен идти до первого клика запуска
    need_pred = player.needs_predicted_start()
    print('карта: %s | объектов: %d | первая нота: %.3f c | первый звук трека: %.3f c'
          % (bm.title, len(bm.hit_objects), first_note, ref_onset))
    print('стратегия старта: %s'
          % ('предсказанный старт (калибровка Δ)' if need_pred else 'прямой старт по онсету'))

    if args.search:
        if not ensure_songselect():
            print('не удалось выйти в song select')
            return 2
        search_in_songselect(args.search)
        print('поиск в song select: %r (выберите сложность вручную при необходимости)' % args.search)

    if not ensure_pause():
        player.stop()
        return 2

    delta = None
    if need_pred:
        if args.delta is not None:
            delta = args.delta
            print('Δ задана вручную: %.3f c' % delta)
        else:
            delta = calibrate_delta(player)
            if delta is None:
                player.stop()
                return 4
        if not ensure_pause():
            player.stop()
            return 2

    # --- бой: всегда из паузы ---
    if not ensure_pause():
        player.stop()
        return 2
    idrv.move_absolute(*PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    print('бой: клик «Повторить» в %.3f' % t_click)

    if need_pred:
        player.predicted_start(t_click, delta)
        player.start_onset_watcher(not_before=t_click + 0.2,
                                   earliest=t_click + EARLIEST_MARGIN,
                                   timeout=12.0, t0=t_click)
        print('бой: T0 ожидается в +%.3f c, первая нота в +%.3f c'
              % (delta, delta + first_note - player.s))
    else:
        t_onset = player.wait_for_onset_anchor(t_click, earliest_margin=EARLIEST_MARGIN,
                                               timeout=15.0)
        if t_onset is None:
            print('бой: онсет не найден — прогон отменён')
            player.stop()
            return 5
        print('бой: якорь по онсету +%.3f c после клика (первая нота в +%.3f c)'
              % (t_onset - t_click, t_onset - t_click + first_note - player.s))

    player.start_relocator()
    import gc
    gc.disable()   # паузы сборщика мусора в момент удара — лишние миллисекунды
    if args.test:
        stats = player.play(until_time_ms=600, verbose=False)
        print('исполнено: %s' % stats)
        idrv.key(27)
        time.sleep(1.5)
        img = grab()
        img.save(args.shot + '_pause.png')
        print('скриншот паузы: %s_pause.png' % args.shot)
        player.stop()
        return 0

    t_play = time.perf_counter()
    stats = player.play(verbose=True)
    print('исполнено: %s (%.1f c)' % (stats, time.perf_counter() - t_play))

    last = max((o.end_time or o.time) for o in bm.hit_objects)
    wait_until = player.wall_time(last) + 15.0
    while time.perf_counter() < wait_until:
        time.sleep(0.5)
    time.sleep(2.0)
    img = grab()
    img.save(args.shot + '_results.png')
    img.resize((1100, 619)).save(args.shot + '_small.png')
    print('скриншот результатов: %s_results.png' % args.shot)
    player.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
