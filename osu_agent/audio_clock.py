"""Аудио-клок: определение текущей позиции музыки в треке карты.

Идея (feed-forward): карта `.osu` известна заранее, значит достаточно знать,
«где сейчас музыка». Захватываем системный вывод (WASAPI loopback) и находим
позицию кросс-корреляцией с эталонным аудиофайлом карты.

Инструмент:
    python -m osu_agent.audio_clock info <audio.mp3>
    python -m osu_agent.audio_clock locate <audio.mp3> --seconds 4
    python -m osu_agent.audio_clock selftest <audio.mp3> --start 30
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 48000
COARSE_SR = 8000  # грубый поиск: разрешение 0.125 мс, FFT в разы меньше


@dataclass
class AudioMatch:
    """Результат локации: позиция в треке и уверенность."""

    position_sec: float
    score: float          # нормированная корреляция (1.0 — идеально)
    coarse_position: float
    duration_sec: float


def load_audio(path: str | Path, sr: int = SR) -> np.ndarray:
    """Прочитать аудио в моно float32 с заданной частотой (линейный ресемплинг)."""
    import soundfile as sf

    data, file_sr = sf.read(str(path), dtype='float32', always_2d=True)
    mono = data.mean(axis=1)
    if file_sr != sr:
        n_out = int(round(len(mono) * sr / file_sr))
        idx = np.linspace(0, len(mono) - 1, n_out, dtype=np.float64)
        mono = np.interp(idx, np.arange(len(mono)), mono).astype(np.float32)
    return mono


def record_loopback(device_name: str, seconds: float, sr: int = SR) -> np.ndarray:
    """Записать системный вывод устройства (WASAPI loopback) в моно float32."""
    import soundcard as sc

    mic = sc.get_microphone(device_name, include_loopback=True)
    data = mic.record(samplerate=sr, numframes=int(sr * seconds))
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    return arr


class BackgroundRecorder:
    """Непрерывный фоновый захват loopback (кольцевой буфер блоков).

    Решает проблему «слепого старта»: блокирующая запись 4 секунд в начале карты
    приводила к пропуску первых нот. Здесь поток пишет звук постоянно, а позиция
    трека берётся в любой момент без остановки планировщика.
    """

    def __init__(self, device_name: str, sr: int = SR, block_sec: float = 0.5, keep_sec: float = 8.0):
        self.device_name = device_name
        self.sr = sr
        self.block = int(sr * block_sec)
        self.keep = int(sr * keep_sec)
        self._blocks: list[tuple[float, np.ndarray]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mic = None

    def start(self) -> "BackgroundRecorder":
        """Запустить фоновую запись (повторный вызов безопасен — no-op)."""
        if self._thread is not None and self._thread.is_alive():
            return self
        import soundcard as sc

        self._mic = sc.get_microphone(self.device_name, include_loopback=True)
        self._thread = threading.Thread(target=self._run, daemon=True, name="loopback-recorder")
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._mic.record(samplerate=self.sr, numframes=self.block)
            except Exception:
                time.sleep(0.1)
                continue
            arr = np.asarray(data, dtype=np.float32)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            t_end = time.perf_counter()
            with self._lock:
                self._blocks.append((t_end, arr))
                total = sum(len(b) for _, b in self._blocks)
                while total > self.keep and len(self._blocks) > 1:
                    total -= len(self._blocks[0][1])
                    self._blocks.pop(0)

    def recent(self, seconds: float) -> tuple[np.ndarray | None, float | None]:
        """Последние `seconds` секунд записи и время конца этого сигнала (perf_counter)."""
        with self._lock:
            blocks = list(self._blocks)
        if not blocks:
            return None, None
        need = int(self.sr * seconds)
        parts: list[tuple[float, np.ndarray]] = []
        total = 0
        for t_end, arr in reversed(blocks):
            parts.append((t_end, arr))
            total += len(arr)
            if total >= need:
                break
        parts.reverse()
        audio = np.concatenate([a for _, a in parts])
        # Конец последнего блока = конец (обрезанного) сигнала: берём последние
        # need сэмплов, их конец совпадает с концом всего накопленного сигнала.
        t_end = parts[-1][0]
        return audio[-need:], t_end

    def locate(self, ref: np.ndarray, seconds: float = 3.0, hint: float | None = None):
        """Позиция трека по последним `seconds` секундам: (позиция_конца, score, t_end).

        `hint` — ожидаемая позиция (сек) для быстрого поиска в окне ±30 с.
        """
        audio, t_end = self.recent(seconds)
        if audio is None or len(audio) < self.sr // 2:
            return None
        pos, score = find_offset(ref, audio, self.sr, hint=hint)
        return pos, score, t_end

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Ресемплинг: при понижении с целым коэффициентом — усреднение (антиалиасинг)."""
    if sr_from == sr_to:
        return x
    if sr_from % sr_to == 0:
        factor = sr_from // sr_to
        n = len(x) - (len(x) % factor)
        return x[:n].reshape(-1, factor).mean(axis=1).astype(np.float32)
    n_out = int(round(len(x) * sr_to / sr_from))
    idx = np.linspace(0, len(x) - 1, n_out, dtype=np.float64)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def _ncc_prepared(seg: np.ndarray, nfft: int, R: np.ndarray, e_ref: np.ndarray,
                  e_seg: float) -> np.ndarray:
    """Нормированная кросс-корреляция окна с эталоном при предвычисленных FFT/энергии.

    R — rfft(ref) фиксированного размера nfft; e_ref — энергия ref в окне для
    каждого лага. Кэширование R даёт ускорение в ~2 раза, а главное — позволяет
    считать полную корреляцию за ~десятки миллисекунд вместо секунд.
    """
    conv = np.fft.irfft(R * np.fft.rfft(seg[::-1], nfft), nfft)
    nv = len(e_ref)
    corr = conv[len(seg) - 1: len(seg) - 1 + nv]
    denom = np.sqrt(np.maximum(e_ref * e_seg, 1e-12))
    return corr / denom


def find_offset(ref: np.ndarray, rec: np.ndarray, sr: int = SR,
                coarse_sr: int = COARSE_SR, window: float = 0.8, step: float = 0.4,
                max_windows: int = 6, hint: float | None = None,
                hint_range: float = 30.0):
    """Позиция записи в эталоне: сумма NCC по нескольким окнам.

    `hint` (сек) ограничивает зону поиска вокруг ожидаемой позиции — используется
    для быстрой периодической перекалибровки (окно ref меньше → FFT короче).
    Возвращает (позиция_конца_записи_в_треке, score). Точность 1/coarse_sr.
    """
    ref_c = _resample(ref, sr, coarse_sr)
    rec_c = _resample(rec, sr, coarse_sr)

    base_offset = 0
    if hint is not None:
        h0 = max(0, int((hint - hint_range) * coarse_sr))
        h1 = min(len(ref_c), int((hint + hint_range) * coarse_sr) + len(rec_c))
        if h1 - h0 > len(rec_c):
            base_offset = h0
            ref_c = ref_c[h0:h1]

    wlen = min(len(rec_c), int(window * coarse_sr))
    step_c = max(1, int(step * coarse_sr))
    if wlen < coarse_sr // 10:
        raise ValueError('слишком короткая запись')

    nfft = 1 << (len(ref_c) + wlen - 1).bit_length()

    # предвычисления, общие для всех окон
    R = np.fft.rfft(ref_c, nfft)
    nv = len(ref_c) - wlen + 1
    cs = np.concatenate(([0.0], np.cumsum(ref_c.astype(np.float64) ** 2)))
    e_ref = cs[wlen:] - cs[:nv]

    acc = np.zeros(len(ref_c) + len(rec_c) + 2, dtype=np.float64)
    count = 0
    starts = list(range(0, len(rec_c) - wlen + 1, step_c))
    if len(starts) > max_windows:
        keep = np.linspace(0, len(starts) - 1, max_windows).astype(int)
        starts = [starts[i] for i in keep]
    for start in starts:
        seg = rec_c[start:start + wlen]
        ncc = _ncc_prepared(seg, nfft, R, e_ref, float(np.sum(seg.astype(np.float64) ** 2)))
        shift = len(rec_c) - start
        acc[shift: shift + len(ncc)] += ncc
        count += 1

    if count == 0:
        raise ValueError('нет полных окон в записи')
    acc /= count
    peak = int(np.argmax(acc))
    score = float(acc[peak])
    duration = len(ref) / sr
    position = min((peak + base_offset) / coarse_sr, duration)
    return position, score


def locate(ref: np.ndarray, rec: np.ndarray, sr: int = SR, hint: float | None = None) -> AudioMatch:
    """Позиция в треке, соответствующая концу записи loopback."""
    pos, score = find_offset(ref, rec, sr, hint=hint)
    dur = len(ref) / sr
    pos = max(0.0, min(pos, dur))
    return AudioMatch(position_sec=pos, score=score, coarse_position=pos, duration_sec=dur)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Аудио-клок osu!-агента")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_info = sub.add_parser('info', help='показать длительность эталона')
    p_info.add_argument('audio')

    p_loc = sub.add_parser('locate', help='записать loopback и найти позицию')
    p_loc.add_argument('audio')
    p_loc.add_argument('--seconds', type=float, default=4.0)
    p_loc.add_argument('--device', default='Speakers (Realtek(R) Audio)')

    p_self = sub.add_parser('selftest', help='проверка без игры: проиграть фрагмент и поймать его')
    p_self.add_argument('audio')
    p_self.add_argument('--start', type=float, default=30.0)
    p_self.add_argument('--seconds', type=float, default=4.0)
    p_self.add_argument('--device', default='Speakers (Realtek(R) Audio)')
    p_self.add_argument('--device-index', type=int, default=15, help='индекс WASAPI-устройства вывода (sounddevice)')

    args = parser.parse_args(argv)

    if args.cmd == 'info':
        ref = load_audio(args.audio)
        print('длительность: %.2f с (%d сэмплов, %d Гц)' % (len(ref) / SR, len(ref), SR))
        return 0

    if args.cmd == 'locate':
        ref = load_audio(args.audio)
        t0 = time.perf_counter()
        rec = record_loopback(args.device, args.seconds)
        t_rec = time.perf_counter() - t0
        m = locate(ref, rec)
        print('запись %.2f с за %.2f с | позиция: %.3f с | score=%.3f | длительность трека %.1f с'
              % (args.seconds, t_rec, m.position_sec, m.score, m.duration_sec))
        return 0

    if args.cmd == 'selftest':
        import sounddevice as sd

        ref = load_audio(args.audio)
        start = args.start
        frag = ref[int(start * SR): int((start + args.seconds) * SR)]
        print('играю фрагмент трека %.1f–%.1f с на устройстве idx=%d' % (start, start + args.seconds, args.device_index))
        sd.play(frag, samplerate=SR, device=args.device_index)
        time.sleep(0.5)
        rec = record_loopback(args.device, args.seconds - 0.5)
        sd.stop()
        m = locate(ref, rec)
        err = m.position_sec - (start + args.seconds)
        print('найдено: %.3f с | ожидалось ~%.3f с | ошибка %.3f с | score=%.3f'
              % (m.position_sec, start + args.seconds, err, m.score))
        return 0

    return 1


if __name__ == '__main__':
    sys.exit(main())
