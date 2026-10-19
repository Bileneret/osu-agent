"""Тесты парсера карт `.osu`."""

from pathlib import Path

from osu_agent.beatmap import Beatmap

SAMPLE = """osu file format v14

[General]
AudioFilename: audio.mp3
AudioLeadIn: 0
Mode: 0

[Metadata]
Title:Test Song
Artist:Test Artist
Creator:Tester
Version:Test Diff
BeatmapID:1
BeatmapSetID:2

[Difficulty]
OverallDifficulty:8
ApproachRate:9
CircleSize:4
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
1000,500,4,2,1,60,1,0
2000,-100,4,2,1,60,0,0

[HitObjects]
100,100,2000,1,0
200,150,2500,2,0,L|300:150,1,140
150,150,4000,8,0,5500
100,100,6000,1,0
"""


def test_format_and_metadata():
    bm = Beatmap.from_text(SAMPLE)
    assert bm.format_version == 14
    assert bm.title == "Test Artist — Test Song [Test Diff]"
    assert bm.mode == 0


def test_difficulty():
    bm = Beatmap.from_text(SAMPLE)
    assert bm.overall_difficulty == 8
    assert bm.approach_rate == 9
    assert bm.difficulty["CircleSize"] == 4


def test_timing_points():
    bm = Beatmap.from_text(SAMPLE)
    assert len(bm.timing_points) == 2
    red, green = bm.timing_points
    assert red.time == 1000 and red.beat_length == 500
    assert red.uninherited is True
    assert red.bpm == 120.0
    assert green.uninherited is False
    assert green.bpm is None
    assert bm.bpm_range() == (120.0, 120.0)


def test_hit_objects():
    bm = Beatmap.from_text(SAMPLE)
    counts = bm.counts()
    assert counts == {"circle": 2, "slider": 1, "spinner": 1, "hold": 0}

    circle, slider, spinner, _ = bm.hit_objects
    assert circle.kind == "circle" and circle.time == 2000
    assert slider.kind == "slider"
    assert slider.curve_type == "L"
    assert slider.curve_points == ((300.0, 150.0),)
    assert slider.slides == 1 and slider.length == 140
    assert spinner.kind == "spinner" and spinner.end_time == 5500


def test_note_times_and_intervals():
    bm = Beatmap.from_text(SAMPLE)
    assert bm.note_times(("circle",)) == [2000.0, 6000.0]
    assert bm.note_times(("circle", "slider")) == [2000.0, 2500.0, 6000.0]
    assert bm.intervals(("circle",)) == [4000.0]
    assert bm.last_object_time == 6000.0


def test_from_file(tmp_path: Path):
    p = tmp_path / "map.osu"
    p.write_text(SAMPLE, encoding="utf-8")
    bm = Beatmap.from_file(p)
    assert bm.path == p
    assert bm.counts()["slider"] == 1
