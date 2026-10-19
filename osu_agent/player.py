"""Исполнитель карты: играет объекты по таймлайну с аудио-клоком.

Полное покрытие osu!standard: круги (тап), слайдеры (KeyDown в голову + ведение
курсора по построенному пути + KeyUp в хвосте), спиннеры (вращение).

Тайминг: позиция трека берётся из фонового loopback-рекордера (`BackgroundRecorder`);
`S` — калиброванный сдвиг (аудио-латентность + ввод), по умолчанию 0.10 с.
"""

from __future__ import annotations

import math
import time

from . import input_driver as idrv
from .audio_clock import BackgroundRecorder
from .beatmap import Beatmap, HitObject
from .slider_path import build_path, point_at_distance

VK_Z = 0x5A
VK_X = 0x58


class MapPlayer:
    """Играет карту: планирует удары по таймлайну `.osu` и исполняет их."""

    def __init__(self, beatmap: Beatmap, ref_audio, device_name: str,
                 s_offset: float = 0.10, lookahead: float = 0.35):
        self.bm = beatmap
        self.ref = ref_audio
        self.device = device_name
        self.s = s_offset
        self.lookahead = lookahead
        self.rec = BackgroundRecorder(device_name)
        self.t_end_pos: float | None = None   # позиция трека на момент t_anchor
        self.t_anchor: float | None = None    # perf_counter

    # ---- синхронизация ----

    def calibrate_position(self, timeout: float = 10.0, min_score: float = 0.30,
                           pair_gap: float = 0.8, pair_tol: float = 0.05) -> tuple[float, float]:
        """Дождаться НАДЁЖНОЙ локации трека (двойная проверка согласованности).

        Одиночная локация в начале карты ненадёжна: в буфере может быть превью из
        меню/тишина, score низкий и пик корреляции ложный. Поэтому берём две
        локации с интервалом `pair_gap` и требуем, чтобы позиция выросла ровно
        на прошедшее время (иначе ждём следующую пару).
        """
        self.rec.start()
        deadline = time.perf_counter() + timeout
        prev = None
        while time.perf_counter() < deadline:
            result = self.rec.locate(self.ref, 2.0)
            if result is not None:
                pos, score, t_end = result
                if prev is not None:
                    pos0, score0, t0 = prev
                    dt = t_end - t0
                    dpos = pos - pos0
                    if score >= min_score and score0 >= min_score and abs(dpos - dt) < pair_tol:
                        self.t_end_pos, self.t_anchor = pos, t_end
                        return pos, score
                prev = (pos, score, t_end)
            time.sleep(pair_gap)
        # не удалось получить согласованную пару — берём последнюю с приличным score
        if prev is not None and prev[1] >= min_score:
            self.t_end_pos, self.t_anchor = prev[0], prev[2]
            return prev[0], prev[1]
        raise RuntimeError('не удалось определить позицию трека (score 0)')

    def start_relocator(self, every: float = 5.0) -> None:
        """Фоновый поток перекалибровки: считает позицию, НЕ блокируя геймплей.

        Раньше перекалибровка вызывалась из основного цикла и блокировала его на
        время БПФ (~секунду) — игровой цикл замирал и ноты выбрасывались как skipped.
        """
        import threading

        self._reloc_stop = threading.Event()
        self._reloc_lock = threading.Lock()
        self._reloc_result = None

        def loop():
            while not self._reloc_stop.is_set():
                hint = None
                if self.t_end_pos is not None:
                    hint = self.t_end_pos + (time.perf_counter() - self.t_anchor)
                try:
                    result = self.rec.locate(self.ref, 2.0, hint=hint)
                except Exception:
                    result = None
                if result is not None:
                    with self._reloc_lock:
                        self._reloc_result = result
                self._reloc_stop.wait(every)

        self._reloc_thread = threading.Thread(target=loop, daemon=True, name='relocator')
        self._reloc_thread.start()

    def apply_relocation(self, tol: float = 0.05) -> None:
        """Применить готовый фоновый замер (если он согласуется с текущими часами)."""
        if getattr(self, '_reloc_lock', None) is None:
            return
        with self._reloc_lock:
            result = self._reloc_result
            self._reloc_result = None
        if result is None:
            return
        pos, score, t_end = result
        if score < 0.30:
            return
        expected = self.t_end_pos + (t_end - self.t_anchor)
        if abs(pos - expected) < tol:
            self.t_end_pos, self.t_anchor = pos, t_end

    def wall_time(self, note_time_ms: float) -> float:
        """Wall-время (perf_counter) для ноты с временем карты `note_time_ms`."""
        return self.t_anchor + (note_time_ms / 1000.0 - self.s - self.t_end_pos)

    def stop(self) -> None:
        if getattr(self, '_reloc_stop', None) is not None:
            self._reloc_stop.set()
        idrv.release_all()
        self.rec.stop()

    # ---- исполнение объектов ----

    def _tap_circle(self, obj: HitObject, t_wall: float) -> None:
        sx, sy = idrv.osu_to_screen(obj.x, obj.y)
        idrv.move_absolute(sx, sy)
        while time.perf_counter() < t_wall:
            pass
        idrv.tap_alternate()

    def _follow_slider(self, obj: HitObject, t_wall: float) -> None:
        path = self.bm.slider_path(obj)
        if path is None or len(path) < 2:
            self._tap_circle(obj, t_wall)
            return
        velocity_ms = self.bm.slider_velocity(obj.time)  # osu-px/МС
        if not velocity_ms:
            self._tap_circle(obj, t_wall)
            return
        velocity_sec = velocity_ms * 1000.0               # osu-px/СЕК (важно: раньше
        # здесь была ошибка размерности в 1000 раз — курсор стоял в головке слайдера)
        length = max(obj.length, 1.0)
        slides = max(obj.slides, 1)
        t_end_wall = t_wall + (obj.end_time - obj.time) / 1000.0 if obj.end_time else t_wall + 0.5

        sx0, sy0 = idrv.osu_to_screen(obj.x, obj.y)
        idrv.move_absolute(sx0, sy0)
        while time.perf_counter() < t_wall:
            pass
        idrv.hold_start(VK_Z)  # держим кнопку на всё тело слайдера (защита от релизера)

        while True:
            now = time.perf_counter()
            if now >= t_end_wall:
                break
            progress = (now - t_wall) * velocity_sec      # пройденный путь, px
            cycles = int(progress // length)
            d = progress - cycles * length
            if cycles % 2 == 1:
                d = length - d                            # обратный ход (слайды > 1)
            x, y = point_at_distance(path, d)
            sx, sy = idrv.osu_to_screen(x, y)
            idrv.move_absolute(sx, sy)
            time.sleep(0.004)
        idrv.hold_end(VK_Z)

    def _spin(self, obj: HitObject, t_wall: float) -> None:
        t_end_wall = t_wall + (obj.end_time - obj.time) / 1000.0 if obj.end_time else t_wall + 1.0
        cx, cy = idrv.osu_to_screen(obj.x, obj.y)
        radius = 120  # экранных пикселей
        period = 0.2  # 5 оборотов в секунду
        idrv.move_absolute(cx + radius, cy)
        while time.perf_counter() < t_wall:
            pass
        idrv.hold_start(VK_Z)  # вращение с зажатой кнопкой
        while True:
            now = time.perf_counter()
            if now >= t_end_wall:
                break
            ang = 2 * math.pi * (now - t_wall) / period
            idrv.move_absolute(int(cx + radius * math.cos(ang)), int(cy + radius * math.sin(ang)))
            time.sleep(0.004)
        idrv.hold_end(VK_Z)
        idrv.move_absolute(cx, cy)

    # ---- основной цикл ----

    def play(self, until_time_ms: float | None = None, verbose: bool = True) -> dict:
        """Играть карту (или до `until_time_ms` времени карты). Вернуть статистику."""
        objs = sorted(self.bm.hit_objects, key=lambda o: o.time)
        stats = {'circles': 0, 'sliders': 0, 'spinners': 0, 'skipped': 0, 'late': 0}

        for obj in objs:
            if until_time_ms is not None and obj.time > until_time_ms:
                break
            t_wall = self.wall_time(obj.time)
            now = time.perf_counter()
            if t_wall < now + 0.05:
                stats['skipped'] += 1
                continue

            # подводим курсор заранее для круга/слайдера
            if obj.kind in ('circle',):
                sx, sy = idrv.osu_to_screen(obj.x, obj.y)
                idrv.move_absolute(sx, sy)

            if obj.kind == 'circle':
                self._tap_circle(obj, t_wall)
                stats['circles'] += 1
            elif obj.kind == 'slider':
                self._follow_slider(obj, t_wall)
                stats['sliders'] += 1
            elif obj.kind == 'spinner':
                self._spin(obj, t_wall)
                stats['spinners'] += 1

            if verbose and (stats['circles'] + stats['sliders'] + stats['spinners']) % 25 == 0:
                print('  ... круги %d, слайдеры %d, спиннеры %d' %
                      (stats['circles'], stats['sliders'], stats['spinners']))

            # применяем готовый фоновый замер (не блокирует цикл)
            self.apply_relocation()
        return stats
