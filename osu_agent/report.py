"""CLI-сводка по картам: объекты, BPM, плотность нот, звёздность.

Запуск:
    python -m osu_agent.report beatmaps/
    python -m osu_agent.report path/to/map.osu --intervals
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from .beatmap import Beatmap, iter_osu_files


def _star_rating(path: Path) -> float | None:
    """Звёздность через rosu-pp (если установлен)."""
    try:
        from rosu_pp_py import Beatmap as RosuBeatmap, Difficulty
    except ImportError:
        return None
    try:
        return Difficulty().calculate(RosuBeatmap(path=str(path))).stars
    except Exception:
        return None


def _fmt(value: float | None, suffix: str = "", nd: int = 2) -> str:
    return f"{value:.{nd}f}{suffix}" if value is not None else "?"


def report_map(path: Path, show_intervals: bool = False) -> None:
    bm = Beatmap.from_file(path)
    counts = bm.counts()
    bpm = bm.bpm_range()
    intervals = bm.intervals(("circle",))

    sr = _star_rating(path)
    print("=" * 96)
    print(bm.title)
    print(
        "  SR %s | OD %.1f AR %.1f CS %s | BPM %s | объекты: круги %d, слайдеры %d, спиннеры %d"
        % (
            _fmt(sr, "*"),
            bm.overall_difficulty,
            bm.approach_rate,
            bm.difficulty.get("CircleSize", "?"),
            f"{bpm[0]:.1f}–{bpm[1]:.1f}" if bpm else "?",
            counts["circle"],
            counts["slider"],
            counts["spinner"],
        )
    )
    print("  длительность: %.1f c | последний объект: %.0f мс" % (bm.last_object_time / 1000.0, bm.last_object_time))

    if intervals:
        half_window = (80 - 6 * bm.overall_difficulty) / 2  # полуокно «300», мс
        tighter = sum(1 for i in intervals if i < half_window * 2)
        print(
            "  интервалы между кругами: медиана %.1f мс, мин %.1f, макс %.1f | теснее окна «300» (±%.2f мс): %d из %d"
            % (
                statistics.median(intervals),
                min(intervals),
                max(intervals),
                half_window,
                tighter,
                len(intervals),
            )
        )
        if show_intervals:
            step = max(1, len(intervals) // 40)
            sample = intervals[::step]
            print("  выборка интервалов, мс:", ", ".join("%.0f" % i for i in sample))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сводка по картам osu! (.osu/.osz)")
    parser.add_argument("paths", nargs="+", help="файлы/папки карт")
    parser.add_argument("--intervals", action="store_true", help="печатать выборку интервалов")
    args = parser.parse_args(argv)

    files: list[Path] = []
    for raw in args.paths:
        files.extend(iter_osu_files(raw))
    if not files:
        print("Не найдено карт .osu")
        return 1

    for path in files:
        report_map(path, show_intervals=args.intervals)
        # временные файлы, распакованные из .osz, убираем
        if "__" in path.stem and path.parent.name == path.parent.name:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
