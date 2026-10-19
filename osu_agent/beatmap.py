"""Парсер формата `.osu` (osu!standard) — первый слой проекта.

Формат открытый и текстовый: секции [General], [Metadata], [Difficulty],
[TimingPoints], [HitObjects]. Нам нужны точные времена нот (мс), координаты,
типы объектов и параметры слайдеров — из этого строится вся дальнейшая
синхронизация (feed-forward: тайминг берём из карты, а не из пикселей).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Биттимапсы карт: какие биты в поле type означают тип объекта.
_TYPE_CIRCLE = 1
_TYPE_SLIDER = 2
_TYPE_SPINNER = 8
_TYPE_HOLD = 128  # osu!mania, для standard не встречается


@dataclass(frozen=True)
class TimingPoint:
    """Точка тайминга: красная (uninherited=True) задаёт BPM, зелёная — SV."""

    time: float
    beat_length: float
    meter: int = 4
    uninherited: bool = True

    @property
    def bpm(self) -> float | None:
        """BPM для красной линии; None — для зелёной (изменение скорости)."""
        if not self.uninherited or self.beat_length <= 0:
            return None
        return 60000.0 / self.beat_length


@dataclass(frozen=True)
class HitObject:
    """Один игровой объект карты."""

    kind: str  # "circle" | "slider" | "spinner" | "hold"
    x: float
    y: float
    time: float
    obj_type: int
    hit_sound: int = 0
    end_time: float | None = None  # слайдер/спиннер: время окончания
    # слайдер:
    curve_type: str | None = None  # L/C/B/P
    curve_points: tuple[tuple[float, float], ...] = ()
    slides: int = 0
    length: float = 0.0

    @property
    def is_circle(self) -> bool:
        return self.kind == "circle"

    @property
    def is_slider(self) -> bool:
        return self.kind == "slider"

    @property
    def is_spinner(self) -> bool:
        return self.kind == "spinner"


@dataclass
class Beatmap:
    """Разобранная карта: метаданные, сложность, тайминги, объекты."""

    path: Path | None = None
    format_version: int = 0
    general: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    difficulty: dict[str, float] = field(default_factory=dict)
    timing_points: list[TimingPoint] = field(default_factory=list)
    hit_objects: list[HitObject] = field(default_factory=list)

    # ---- свойства, удобные для планирования ----

    @property
    def title(self) -> str:
        artist = self.metadata.get("Artist", "?")
        title = self.metadata.get("Title", "?")
        version = self.metadata.get("Version", "?")
        return f"{artist} — {title} [{version}]"

    @property
    def overall_difficulty(self) -> float:
        return self.difficulty.get("OverallDifficulty", 5.0)

    @property
    def approach_rate(self) -> float:
        return self.difficulty.get("ApproachRate", 5.0)

    @property
    def mode(self) -> int:
        return int(self.general.get("Mode", "0"))

    def note_times(self, kinds: tuple[str, ...] = ("circle",)) -> list[float]:
        """Времена объектов заданных типов (по умолчанию — только круги)."""
        return sorted(o.time for o in self.hit_objects if o.kind in kinds)

    def intervals(self, kinds: tuple[str, ...] = ("circle",)) -> list[float]:
        """Интервалы (мс) между последовательными объектами — метрика плотности."""
        times = self.note_times(kinds)
        return [b - a for a, b in zip(times, times[1:])]

    def bpm_range(self) -> tuple[float, float] | None:
        """Диапазон BPM по красным линиям тайминга (min, max)."""
        bpms = [tp.bpm for tp in self.timing_points if tp.bpm]
        if not bpms:
            return None
        return min(bpms), max(bpms)

    def counts(self) -> dict[str, int]:
        """Сколько объектов каждого типа в карте."""
        result: dict[str, int] = {"circle": 0, "slider": 0, "spinner": 0, "hold": 0}
        for obj in self.hit_objects:
            result[obj.kind] = result.get(obj.kind, 0) + 1
        return result

    @property
    def last_object_time(self) -> float:
        """Время последнего события карты (учитывая концы слайдеров/спиннеров)."""
        latest = 0.0
        for obj in self.hit_objects:
            latest = max(latest, obj.time, obj.end_time or 0.0)
        return latest

    # ---- разбор ----

    @classmethod
    def from_file(cls, path: str | Path) -> "Beatmap":
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        bm = cls.from_text(text)
        bm.path = path
        return bm

    @classmethod
    def from_text(cls, text: str) -> "Beatmap":
        bm = cls()
        section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line
                continue
            if section == "" and line.lower().startswith("osu file format"):
                bm.format_version = _parse_format_version(line)
                continue
            parser = _SECTION_PARSERS.get(section)
            if parser is not None:
                parser(bm, line)
        return bm


def _parse_format_version(line: str) -> int:
    parts = line.split("v")
    return int(parts[-1]) if parts[-1].isdigit() else 0


def _kv(line: str) -> tuple[str, str]:
    key, _, value = line.partition(":")
    return key.strip(), value.strip()


def _parse_general(bm: Beatmap, line: str) -> None:
    key, value = _kv(line)
    bm.general[key] = value


def _parse_metadata(bm: Beatmap, line: str) -> None:
    key, value = _kv(line)
    bm.metadata[key] = value


def _parse_difficulty(bm: Beatmap, line: str) -> None:
    key, value = _kv(line)
    try:
        bm.difficulty[key] = float(value)
    except ValueError:
        bm.difficulty[key] = value  # SliderMultiplier бывает строкой в старых картах


def _parse_timing_point(bm: Beatmap, line: str) -> None:
    parts = line.split(",")
    if len(parts) < 2:
        return
    try:
        time = float(parts[0])
        beat_length = float(parts[1])
    except ValueError:
        return
    meter = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 4
    uninherited = parts[6].strip() == "1" if len(parts) > 6 else True
    bm.timing_points.append(
        TimingPoint(time=time, beat_length=beat_length, meter=meter, uninherited=uninherited)
    )


def _parse_hit_object(bm: Beatmap, line: str) -> None:
    parts = line.split(",")
    if len(parts) < 5:
        return
    try:
        x, y, time, obj_type = float(parts[0]), float(parts[1]), float(parts[2]), int(parts[3])
        hit_sound = int(parts[4])
    except ValueError:
        return

    if obj_type & _TYPE_CIRCLE:
        kind = "circle"
    elif obj_type & _TYPE_SLIDER:
        kind = "slider"
    elif obj_type & _TYPE_SPINNER:
        kind = "spinner"
    elif obj_type & _TYPE_HOLD:
        kind = "hold"
    else:
        return

    end_time: float | None = None
    curve_type: str | None = None
    curve_points: tuple[tuple[float, float], ...] = ()
    slides = 0
    length = 0.0

    if kind == "slider" and len(parts) >= 8:
        curve_raw = parts[5]
        if "|" in curve_raw:
            head, *points_raw = curve_raw.split("|")
            curve_type = head
            pts = []
            for p in points_raw:
                if ":" in p:
                    px, _, py = p.partition(":")
                    try:
                        pts.append((float(px), float(py)))
                    except ValueError:
                        pass
            curve_points = tuple(pts)
        try:
            slides = int(parts[6])
            length = float(parts[7])
        except ValueError:
            pass
    elif kind == "spinner" and len(parts) > 5:
        try:
            end_time = float(parts[5])
        except ValueError:
            pass

    bm.hit_objects.append(
        HitObject(
            kind=kind,
            x=x,
            y=y,
            time=time,
            obj_type=obj_type,
            hit_sound=hit_sound,
            end_time=end_time,
            curve_type=curve_type,
            curve_points=curve_points,
            slides=slides,
            length=length,
        )
    )


_SECTION_PARSERS = {
    "[General]": _parse_general,
    "[Metadata]": _parse_metadata,
    "[Difficulty]": _parse_difficulty,
    "[TimingPoints]": _parse_timing_point,
    "[HitObjects]": _parse_hit_object,
}


def iter_osu_files(path: str | Path) -> Iterator[Path]:
    """Найти все `.osu` по пути: файл, папка (рекурсивно, включая `.osz`) или `.osz` (zip)."""
    import zipfile

    path = Path(path)
    if path.is_dir():
        for found in sorted(path.rglob("*.osu")) + sorted(path.rglob("*.osz")):
            yield from iter_osu_files(found)
        return
    if path.suffix.lower() == ".osz":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".osu"):
                    # распаковываем во временный файл рядом
                    tmp = path.with_name(path.stem + "__" + Path(name).name)
                    tmp.write_bytes(z.read(name))
                    yield tmp
        return
    yield path
