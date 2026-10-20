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
from .audio_clock import BackgroundRecorder, first_sound_time
from .beatmap import Beatmap, HitObject
from .slider_path import build_path, point_at_distance

VK_Z = 0x5A
VK_X = 0x58

DEFAULT_TAP_HOLD_MS = 25.0   # обычное удержание клавиши на тапе
DENSE_TAP_HOLD_MS = 18.0     # плотные стримы: короче, чтобы клавиша успела «сброситься»
DENSE_LEAD_SPEED = 6.0       # px/мс: оценка перелёта на плотных картах
DENSE_TAIL_HOLD = 0.005      # удержание хвоста слайдера на плотных картах
DEFAULT_TAIL_HOLD = 0.015    # обычное удержание хвоста слайдера


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
        self.ref_onset: float = first_sound_time(ref_audio)  # время первого звука трека
        self._send_errs: list[float] = []     # телеметрия: задержка отправки удара
        # кинематика (уточняется auto_tune по плотности карты)
        self.dense: bool = False
        self.min_gap_ms: float | None = None
        self.lead_speed_px_ms: float = 2.5
        self.tap_hold_ms: float = DEFAULT_TAP_HOLD_MS
        self.tail_hold_sec: float = DEFAULT_TAIL_HOLD

    # ---- синхронизация ----

    def wait_for_music_start(self, timeout: float = 40.0) -> float | None:
        """Мгновенный якорь старта: ждём появление звука карты в loopback.

        В отличие от БПФ-локализации не требует накопления секунд музыки и
        не пропускает начало карты. Привязка: слышимый первый звук трека
        (ref_onset) в момент его появления в записи.
        """
        self.rec.start()
        t_onset = self.rec.wait_for_onset(timeout=timeout)
        if t_onset is None:
            return None
        self.t_end_pos = self.ref_onset
        self.t_anchor = t_onset
        return t_onset

    def needs_predicted_start(self, threshold_sec: float = 1.5) -> bool:
        """Нужен ли предсказанный старт для первой ноты карты.

        Тап по первой ноте происходит в T0 + (t_first − S), а первый звук трека
        детектируется не раньше T0 + ref_onset + ~0.1 с. Если первая нота позже
        этого окна (по умолчанию — от 1.5 с), карта стартует напрямую по онсету,
        без калибровки Δ. Предсказание нужно только для карт с очень ранней
        первой нотой (как pearto's Easy: 140 мс при первом звуке 115 мс).
        """
        first_sec = min(o.time for o in self.bm.hit_objects) / 1000.0
        return first_sec < threshold_sec

    def wait_for_onset_anchor(self, t_click: float, earliest_margin: float = 0.55,
                              timeout: float = 15.0) -> float | None:
        """Прямой старт: дождаться фактического первого звука и привязаться к нему.

        `earliest_margin` — минимальная задержка после клика запуска: раньше этого
        момента онсетов быть не может (звук клика по кнопке идёт ~0.13–0.43 с).
        """
        self.rec.start()
        t_onset = self.rec.wait_for_onset(timeout=timeout, poll=0.02,
                                          earliest=t_click + earliest_margin)
        if t_onset is None:
            return None
        self.t_end_pos = self.ref_onset
        self.t_anchor = t_onset
        return t_onset

    def wait_for_position_anchor(self, timeout: float = 25.0, min_score: float = 0.22,
                                 hint: float = 0.0):
        """Прямой старт по КОРРЕЛЯЦИИ: якорь — начало трека, найденное по форме сигнала.

        Нужен для карт с тихим вступлением: детект по громкости не срабатывает, если
        первый звук тише фонового уровня. Первые `timeout/2` ищем в окне у нуля
        (дешёво, защищает от превью), дальше — по всему треку.

        Окно анализа растёт прогрессивно (0.5 → 1.0 → 1.5 → 2.5 с), порог корреляции
        низкий (0.22): на тихом вступлении сигнал слабый, но форма уже узнаваема.
        Так якорь удаётся получить на ~0.5–1 с раньше — именно этого не хватало
        первым нотам kate said (5.66–6.33 с): без этого терялось до 5 объектов.

        ВАЖНО про `s_offset`: корреляционная привязка даёт «истинное» начало трека,
        а RMS-детект — позже (порог громкости пересекается на атаке). Калибровка
        S=0.10 получена с RMS-якорем, поэтому при корреляционном якоре S ≈ 0.095.
        """
        self.rec.start()
        t_start = time.perf_counter()
        deadline = t_start + timeout
        best = None
        prev = None
        while time.perf_counter() < deadline:
            elapsed = time.perf_counter() - t_start
            seconds = (0.5 if elapsed < 2.0 else
                       1.0 if elapsed < 5.0 else
                       1.5 if elapsed < 9.0 else 2.5)
            search_hint = hint if elapsed < timeout / 2 else None
            res = self.rec.locate(self.ref, seconds, hint=search_hint)
            if res is not None:
                pos, score, t_end = res
                if best is None or score > best[1]:
                    best = (pos, score, t_end)
                if score >= min_score and -0.5 <= pos <= 12.0:
                    # требуем согласованности: позиция должна расти ровно со временем
                    # (одна локация на тихом вступлении может быть ложной)
                    if prev is not None:
                        pos0, t0 = prev
                        if abs((pos - pos0) - (t_end - t0)) < 0.05:
                            self.t_end_pos, self.t_anchor = pos, t_end
                            return t_end - pos
                    prev = (pos, t_end)
            time.sleep(0.02)
        if best is not None:
            print('  корреляция: лучший score %.2f (позиция %.2f) — ниже порога %.2f'
                  % (best[1], best[0], min_score))
        return None

    def validate_anchor_by_correlation(self, tol: float = 0.08, timeout: float = 8.0,
                                       min_score: float = 0.35) -> bool:
        """Проверить стартовый якорь по корреляции; при расхождении — переключиться.

        Нужно для карт с тихим вступлением: детект по громкости ловит не первый
        звук трека, а первый громкий (на kate said — на +1.95 с позже), и вся
        шкала уезжает. Корреляция не зависит от громкости.

        Возвращает True, если привязка заменена на корреляционную.
        """
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            expected = self.t_end_pos + (time.perf_counter() - self.t_anchor)
            res = self.rec.locate(self.ref, 1.5, hint=expected)
            if res is not None:
                pos, score, t_end = res
                if score >= min_score:
                    err = pos - (self.t_end_pos + (t_end - self.t_anchor))
                    if abs(err) > tol:
                        self.t_anchor, self.t_end_pos = t_end, pos
                        return True
                    return False
            time.sleep(0.05)
        return False

    def start_position_watcher(self, timeout: float = 25.0, min_score: float = 0.45,
                               seconds: float = 4.0) -> None:
        """Фоновый поток: точный корреляционный T0 для коррекции предсказанного старта.

        Нужен там, где корреляция не успевает к первой ноте (тихое вступление), но
        предсказание Δ уже играет первые ноты: как только сигнал становится громким,
        watcher даёт точную пару (t_end, позиция) — и шкала «прилипает» к реальности.
        Длинная запись (4 с) и высокий порог score (0.45) — чтобы пик корреляции
        был резким: на kate said короткие окна давали разброс ±60 мс.
        """
        import threading
        self._pos_lock = threading.Lock()
        self._pos_actual = None
        self.rec.start()

        def loop():
            deadline = time.perf_counter() + timeout
            while time.perf_counter() < deadline:
                res = self.rec.locate(self.ref, seconds, hint=0.0)
                if res is not None:
                    pos, score, t_end = res
                    if score >= min_score and 0.5 <= pos <= 30.0:
                        with self._pos_lock:
                            self._pos_actual = (t_end, pos)
                        print('  [pos-watcher] корреляция: позиция %.2f c, score %.2f'
                              % (pos, score))
                        return
                time.sleep(0.05)
            print('  [pos-watcher] позиция не найдена за %.0f c' % timeout)

        threading.Thread(target=loop, daemon=True, name='pos-watcher').start()

    def apply_position_correction(self, tol: float = 1.0) -> float | None:
        """Применить точный корреляционный якорь к предсказанной привязке (однократно)."""
        if getattr(self, '_pos_lock', None) is None or not getattr(self, '_predicted', False):
            return None
        with self._pos_lock:
            res = self._pos_actual
            self._pos_actual = None
        if res is None:
            return None
        t_end, pos = res
        self._predicted = False
        expected = self.t_end_pos + (t_end - self.t_anchor)
        err = pos - expected
        if abs(err) > tol:
            return None
        self.t_anchor, self.t_end_pos = t_end, pos
        return err

    def measure_delta_precise(self, t_click: float, timeout: float = 22.0,
                              min_score: float = 0.45, seconds: float = 4.0):
        """Точный замер Δ: длинная запись, длинное окно, двойная согласованность.

        На картах с повторяющимся битом (kate said: lo-fi) корреляция по короткому
        окну даёт широкий пик (±30–60 мс). Больше данных → резче пик: в калибровке
        можно позволить себе 4 секунды записи, потому что мы не играем.
        """
        self.rec.start()
        deadline = time.perf_counter() + timeout
        prev = None
        while time.perf_counter() < deadline:
            res = self.rec.locate(self.ref, seconds, hint=0.0)
            if res is not None:
                pos, score, t_end = res
                if score >= min_score and 0.5 <= pos <= 20.0:
                    if prev is not None:
                        pos0, t0 = prev
                        if abs((pos - pos0) - (t_end - t0)) < 0.02:
                            self.t_end_pos, self.t_anchor = pos, t_end
                            return (t_end - pos) - t_click
                    prev = (pos, t_end)
            time.sleep(0.05)
        return None

    def predicted_start(self, t_click: float, delta: float) -> float:
        """Привязка по ПРЕДСКАЗАНИЮ старта: t_onset = t_click + delta + ref_onset.

        Нужна для нот, которые звучат раньше, чем физически возможен аудио-детект.
        Первый объект карты — слайдер на 140 мс при первом звуке трека 115 мс и
        компенсации S=0.10: тап по нему обязан произойти в T0+0.04, то есть за
        75 мс до первого слышимого звука. `delta` — калиброванная задержка
        «клик запуска → старт трека» (измеряется по онсету на прогреве).
        """
        self.t_end_pos = self.ref_onset
        self.t_anchor = t_click + delta + self.ref_onset
        self._predicted = True
        return self.t_anchor

    def start_onset_watcher(self, not_before: float | None = None,
                            timeout: float = 10.0, poll: float = 0.02,
                            t0: float | None = None,
                            earliest: float | None = None) -> None:
        """Фоновый поток: поймать фактический онсет и уточнить предсказание.

        `earliest` (perf_counter) — фильтр кандидатов: всё раньше этого момента
        отбрасывается (звук клика по кнопке паузы). `not_before` — с какого
        момента начинать слушать (обычно = earliest). `t0` — метка клика для журнала.
        """
        import threading
        self._onset_lock = threading.Lock()
        self._onset_actual = None
        self.rec.start()
        if earliest is None:
            earliest = not_before

        def loop():
            wait = 0.0 if not_before is None else not_before - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            t = self.rec.wait_for_onset(timeout=timeout, poll=poll, earliest=earliest)
            with self._onset_lock:
                self._onset_actual = t
            if t is None:
                print('  [watcher] онсет не найден')
            elif t0 is not None:
                print('  [watcher] онсет +%.3f c после клика' % (t - t0))

        threading.Thread(target=loop, daemon=True, name='onset-watcher').start()

    def apply_onset_correction(self, tol: float = 0.60) -> float | None:
        """Применить фактический онсет к привязке (однократно).

        Возвращает поправку (факт − предсказание) или None. Поправка больше `tol`
        означает, что предсказание было ошибочным — тогда якорь не трогаем, чтобы
        не сорвать уже идущий прогон.
        """
        if getattr(self, '_onset_lock', None) is None or not getattr(self, '_predicted', False):
            return None
        with self._onset_lock:
            t = self._onset_actual
        if t is None:
            return None
        self._predicted = False
        err = t - self.t_anchor
        if abs(err) <= tol:
            self.t_anchor = t
            self.t_end_pos = self.ref_onset
            return err
        return None

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

    def apply_relocation(self, tol: float = 0.25, gain: float = 0.15) -> None:
        """Применить готовый фоновый замер: плавный сдвиг фазы часов (PLL), не скачок.

        Проверка: жёсткая замена `t_anchor = t_end` давала мгновенный скачок фазы на
        шум корреляции (±2–5 мс), что на окне OD10 (±10 мс) выбрасывало удары в OK.
        Здесь ошибка подмешивается с коэффициентом `gain`: часы «догоняют» реальный
        звук за несколько замеров, без разрывов. `tol` — защита от мусорных локаций.
        """
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
        err = pos - expected
        if abs(err) >= tol:
            return
        self.t_anchor -= err * gain

    def wall_time(self, note_time_ms: float) -> float:
        """Wall-время (perf_counter) для ноты с временем карты `note_time_ms`."""
        return self.t_anchor + (note_time_ms / 1000.0 - self.s - self.t_end_pos)

    def stop(self) -> None:
        if getattr(self, '_reloc_stop', None) is not None:
            self._reloc_stop.set()
        idrv.release_all()
        self.rec.stop()

    # ---- исполнение объектов ----

    @staticmethod
    def _wait_until(t_wall: float) -> None:
        """Точное ожидание до t_wall без длинного busy-wait.

        Чистый spin-wait в главном потоке вытесняет поток loopback-записи по GIL:
        блоки захвата приходят с разрывами, и t_end перестаёт соответствовать
        концу записанного сигнала (оценка онсета уезжает на десятки мс).
        Короткий sleep + спин < 3 мс даёт ту же точность без голодания потоков.
        """
        wait = t_wall - time.perf_counter()
        if wait > 0.003:
            time.sleep(wait - 0.002)
        while time.perf_counter() < t_wall:
            pass

    @staticmethod
    def move_lead_sec(distance_px: float, speed_px_ms: float = 2.5,
                      min_lead: float = 0.030, max_lead: float = 0.250) -> float:
        """Сколько времени заложить на «перелёт» курсора к объекту (сек).

        Движение мыши не мгновенно с точки зрения игры: позиция обрабатывается
        input-потоком, и если переместить курсор вплотную к моменту удара, игра
        может судить удар по старой позиции. Считаем оценку time = путь / скорость
        и начинаем движение за это время до удара.
        """
        lead = distance_px / (speed_px_ms * 1000.0)
        return min(max(lead, min_lead), max_lead)

    def auto_tune(self, dense_interval_ms: float = 70.0) -> None:
        """Настроить кинематику по плотности карты (без ручных подборов).

        На плотных картах (минимальный интервал < 70 мс, как kate said: 49 мс)
        длинное упреждение и удержание клавиши съедают время на перелёт курсора.
        Включаем «плотный» режим: быстрее считаем перелёт (6 px/мс) и короче
        держим клавишу (18 мс вместо 25).
        """
        objs = sorted(self.bm.hit_objects, key=lambda o: o.time)
        gaps = [objs[i + 1].time - objs[i].time for i in range(len(objs) - 1)]
        self.min_gap_ms = min(gaps) if gaps else 1000.0
        self.dense = self.min_gap_ms < dense_interval_ms
        self.lead_speed_px_ms = DENSE_LEAD_SPEED if self.dense else 2.5
        self.tap_hold_ms = DENSE_TAP_HOLD_MS if self.dense else DEFAULT_TAP_HOLD_MS
        self.tail_hold_sec = DENSE_TAIL_HOLD if self.dense else DEFAULT_TAIL_HOLD

    @staticmethod
    def tail_hold_sec_for(margin_sec: float | None, default: float,
                          min_hold: float = 0.003, fraction: float = 0.25) -> float:
        """Удержание хвоста слайдера с оглядкой на следующий объект.

        Проверка: на серии слайдеров длительностью 47.5 мс с интервалом 95 мс
        фиксированные 15 мс удержания оставляли всего 32.5 мс на перелёт через
        весь экран — голова следующего слайдера терялась (2 MISS на kate said).
        """
        if margin_sec is None:
            return default
        return min(default, max(min_hold, margin_sec * fraction))

    def _move_with_lead(self, sx: int, sy: int, t_wall: float) -> None:
        """Подвести курсор к (sx, sy) с упреждением по времени перелёта."""
        cx, cy = idrv.cursor_pos()
        lead = self.move_lead_sec(math.hypot(sx - cx, sy - cy), self.lead_speed_px_ms)
        t_move = t_wall - lead
        now = time.perf_counter()
        if now < t_move:
            time.sleep(t_move - now)
        idrv.move_absolute(sx, sy)

    def _tap_circle(self, obj: HitObject, t_wall: float) -> None:
        sx, sy = idrv.osu_to_screen(obj.x, obj.y)
        self._move_with_lead(sx, sy, t_wall)
        self._wait_until(t_wall)
        self._send_errs.append(time.perf_counter() - t_wall)
        idrv.tap_alternate(hold_ms=self.tap_hold_ms)

    def _follow_slider(self, obj: HitObject, t_wall: float,
                       t_next_wall: float | None = None) -> None:
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
        self._move_with_lead(sx0, sy0, t_wall)
        self._wait_until(t_wall)
        self._send_errs.append(time.perf_counter() - t_wall)
        # клавиша, которая точно свободна: KeyUp предыдущего тапа может ещё идти
        vk = idrv.free_key((VK_Z, VK_X))
        idrv.hold_start(vk)  # держим кнопку на всё тело слайдера (защита от релизера)

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
        # удержание хвоста: фиксируем курсор на конечной точке. На плотных картах
        # удержание сокращается пропорционально запасу до следующего объекта —
        # иначе на коротких слайдерах (47 мс) не остаётся времени на перелёт.
        x, y = point_at_distance(path, length)
        idrv.move_absolute(*idrv.osu_to_screen(x, y))
        margin = None if t_next_wall is None else (t_next_wall - t_end_wall)
        time.sleep(self.tail_hold_sec_for(margin, self.tail_hold_sec))
        idrv.hold_end(vk)

    def _spin(self, obj: HitObject, t_wall: float) -> None:
        t_end_wall = t_wall + (obj.end_time - obj.time) / 1000.0 if obj.end_time else t_wall + 1.0
        cx, cy = idrv.osu_to_screen(obj.x, obj.y)
        radius = 80    # экранных пикселей
        period = 0.135  # ~444 RPM: за 4.8 с спиннера даёт ~35 оборотов (нужно 24)
        self._move_with_lead(cx + radius, cy, t_wall)
        self._wait_until(t_wall)
        vk = idrv.free_key((VK_Z, VK_X))
        idrv.hold_start(vk)  # вращение с зажатой кнопкой
        while True:
            now = time.perf_counter()
            if now >= t_end_wall:
                break
            ang = 2 * math.pi * (now - t_wall) / period
            idrv.move_absolute(int(cx + radius * math.cos(ang)), int(cy + radius * math.sin(ang)))
            time.sleep(0.003)
        idrv.hold_end(vk)
        idrv.move_absolute(cx, cy)

    # ---- основной цикл ----

    def play(self, until_time_ms: float | None = None, verbose: bool = True) -> dict:
        """Играть карту (или до `until_time_ms` времени карты). Вернуть статистику."""
        objs = sorted(self.bm.hit_objects, key=lambda o: o.time)
        stats = {'circles': 0, 'sliders': 0, 'spinners': 0, 'skipped': 0, 'late': 0}

        for idx, obj in enumerate(objs):
            if until_time_ms is not None and obj.time > until_time_ms:
                break
            t_wall = self.wall_time(obj.time)
            t_next_wall = (self.wall_time(objs[idx + 1].time)
                           if idx + 1 < len(objs) else None)
            now = time.perf_counter()
            # «догон»: если расчётное время уже прошло, но недавно (<150 мс) — играем
            # немедленно (голова слайдера сама догонит путь через прогресс), иначе пропуск
            if t_wall < now - 0.15:
                stats['skipped'] += 1
                late_by = now - t_wall
                stats.setdefault('skipped_info', []).append(
                    '%s t=%.0f мс (опоздание %.0f мс)' % (obj.kind, obj.time, late_by * 1000))
                if verbose and len(stats['skipped_info']) <= 10:
                    print('  ПРОПУСК: %s t=%.0f мс (опоздание %.0f мс)'
                          % (obj.kind, obj.time, late_by * 1000))
                continue

            # курсор подводится с упреждением внутри обработчиков (_move_with_lead)
            if obj.kind == 'circle':
                self._tap_circle(obj, t_wall)
                stats['circles'] += 1
            elif obj.kind == 'slider':
                self._follow_slider(obj, t_wall, t_next_wall)
                stats['sliders'] += 1
            elif obj.kind == 'spinner':
                self._spin(obj, t_wall)
                stats['spinners'] += 1

            if verbose and (stats['circles'] + stats['sliders'] + stats['spinners']) % 25 == 0:
                print('  ... круги %d, слайдеры %d, спиннеры %d' %
                      (stats['circles'], stats['sliders'], stats['spinners']))

            # уточняем предсказанный якорь фактическим онсетом (один раз)
            err = self.apply_onset_correction()
            if err is not None:
                stats['onset_err'] = err
                if verbose:
                    print('  якорь уточнён по онсету: поправка %+.0f мс' % (err * 1000.0))

            # уточняем предсказанный якорь точной корреляцией (один раз)
            pos_err = self.apply_position_correction()
            if pos_err is not None:
                stats['pos_err'] = pos_err
                if verbose:
                    print('  якорь уточнён по корреляции: поправка %+.0f мс' % (pos_err * 1000.0))

            # применяем готовый фоновый замер (не блокирует цикл)
            self.apply_relocation()
        if self._send_errs:
            errs = sorted(self._send_errs)
            n = len(errs)
            stats['send_p50_ms'] = round(errs[n // 2] * 1000, 2)
            stats['send_p95_ms'] = round(errs[min(n - 1, int(n * 0.95))] * 1000, 2)
            stats['send_max_ms'] = round(errs[-1] * 1000, 2)
        return stats
