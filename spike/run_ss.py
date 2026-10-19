"""SS-прогон карты: предсказанный старт для первого объекта + полное покрытие.

Схема:
  1) ensure_pause()      — привести игру к паузе (зелёная «Продолжить» на экране);
  2) калибровка Δ        — 2 замера «клик Повторить → онсет» (прогрев системы);
  3) боевой прогон       — клик Повторить, привязка по предсказанию, играем всю карту,
                           фактический онсет уточняет якорь для всех нот, начиная со второй;
  4) ждём экран результатов и сохраняем скриншот.

Запуск: python spike/run_ss.py [delta]
"""
import io
import statistics
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
DEV = 'Speakers (Realtek(R) Audio)'

PLAY_BTN = (1810, 1005)
PAUSE_CONTINUE = (960, 428)
PAUSE_RETRY = (960, 535)
PAUSE_EXIT = (960, 655)
RESULTS_BACK = (110, 1048)   # центр розовой «Назад» на экране результатов


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
    for i in range(tries):
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


def calibrate_once(player, timeout=8.0):
    """Клик «Повторить» -> замер T0 − t_click по онсету.

    `earliest=t_click+1.0` отсекает звуки интерфейса (клик по кнопке): до первого
    звука музыки карта проходит интро ≈1.86 с, раньше этого момента онсета быть
    не может. Значение вне [2.0, 5.0] с считается выбросом.
    """
    idrv.move_absolute(*PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    t_onset = player.rec.wait_for_onset(timeout=timeout, poll=0.02, earliest=t_click + 1.0)
    if t_onset is None:
        print('  калибровка: онсет не найден')
        return None
    delta = (t_onset - player.ref_onset) - t_click
    if not (2.0 <= delta <= 5.0):
        print('  калибровка: Δ = %.3f c — выброс, отброшен' % delta)
        return None
    print('  калибровка: Δ = %.3f c' % delta)
    return delta


def main():
    delta_fixed = float(sys.argv[1]) if len(sys.argv) > 1 else None

    hwnd = idrv.find_window()
    print('activate:', idrv.activate(hwnd), '| foreground:', idrv.foreground_title())
    time.sleep(0.4)

    bm = Beatmap.from_file(OSU_TMP)
    ref = load_audio(REF)
    player = MapPlayer(bm, ref, DEV, s_offset=0.10)
    player.rec.start()
    time.sleep(0.5)

    if not ensure_pause():
        player.stop()
        sys.exit(2)

    # --- калибровка ---
    if delta_fixed is not None:
        delta = delta_fixed
        print('Δ задана вручную: %.3f c' % delta)
    else:
        deltas = []
        for i in range(5):
            if len(deltas) >= 2 and (max(deltas) - min(deltas)) <= 0.06:
                break
            d = calibrate_once(player)
            if d is not None:
                deltas.append(d)
            if not ensure_pause():
                player.stop()
                sys.exit(2)
        if len(deltas) < 2:
            print('калибровка не удалась (нет двух валидных замеров)')
            player.stop()
            sys.exit(3)
        spread = max(deltas) - min(deltas)
        if spread > 0.08:
            print('калибровка нестабильна: разброс %.0f мс — прогон отменён' % (spread * 1000))
            player.stop()
            sys.exit(4)
        delta = statistics.mean(deltas)
        print('Δ = %.3f c (замеры: %s)' % (delta, ', '.join('%.3f' % d for d in deltas)))

    # бой обязан начинаться из паузы: иначе клик «Повторить» попадёт в игровое поле
    if not ensure_pause():
        player.stop()
        sys.exit(2)

    # --- боевой прогон ---
    idrv.move_absolute(*PAUSE_RETRY)
    time.sleep(0.08)
    t_click = time.perf_counter()
    idrv.click()
    print('бой: клик «Повторить» в %.3f' % t_click)
    player.predicted_start(t_click, delta)
    player.start_onset_watcher(not_before=t_click + 2.0, timeout=6.0, t0=t_click)
    print('бой: T0 ожидается в +%.3f c, первая нота (140 мс) в +%.3f c'
          % (delta, delta + 0.140 - player.s))
    player.start_relocator()

    t_play_start = time.perf_counter()
    stats = player.play(verbose=True)
    print('исполнено: %s (%.1f c)' % (stats, time.perf_counter() - t_play_start))

    # --- ждём результаты ---
    last = max((o.end_time or o.time) for o in bm.hit_objects)
    wait_until = player.wall_time(last) + 15.0
    while time.perf_counter() < wait_until:
        time.sleep(0.5)
    time.sleep(2.0)
    img = grab()
    img.save('spike/shots/130_results_ss.png')
    img.resize((1100, 619)).save('spike/shots/130_small.png')
    print('скриншот результатов: spike/shots/130_results_ss.png')
    player.stop()


if __name__ == '__main__':
    main()
