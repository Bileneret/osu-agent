"""Тесты геометрии слайдеров: длительность (SV) и путь (сплайны)."""

import numpy as np

from osu_agent.beatmap import Beatmap
from osu_agent.slider_path import build_path, path_length, point_at_distance

SAMPLE = """osu file format v14

[General]
Mode: 0

[Metadata]
Title:Test
Artist:Test
Version:Test

[Difficulty]
OverallDifficulty:5
ApproachRate:5
CircleSize:4
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
1000,500,4,2,1,60,1,0
3000,-50,4,2,1,60,0,0

[HitObjects]
100,100,2000,2,0,L|300:100,1,200
100,100,4000,2,0,L|300:100,1,200
100,100,6000,8,0,7000
"""


def test_slider_end_time_basic():
    bm = Beatmap.from_text(SAMPLE)
    sliders = [o for o in bm.hit_objects if o.kind == 'slider']
    assert len(sliders) == 2
    # velocity = 100 * 1.4 * SV / beatLength; beatLength = 500 мс, SV=1 → 0.28 px/мс
    # длительность = 200 / 0.28 = 714.3 мс
    first = sliders[0]
    assert first.end_time is not None
    assert abs((first.end_time - first.time) - 200 / 0.28) < 1.0
    # второй слайдер после зелёной линии SV=2 (beatLength=-50) → вдвое быстрее
    second = sliders[1]
    assert second.end_time is not None
    assert abs((second.end_time - second.time) - 200 / (0.28 * 2)) < 1.0


def test_sv_and_velocity():
    bm = Beatmap.from_text(SAMPLE)
    assert bm.sv_at(1500) == 1.0
    assert bm.sv_at(3500) == 2.0
    assert abs(bm.slider_velocity(1500) - 0.28) < 1e-9
    assert abs(bm.slider_velocity(3500) - 0.56) < 1e-9


def test_linear_path_length():
    path = build_path('L', [(0.0, 0.0), (100.0, 0.0)], 100.0)
    assert abs(path_length(path) - 100.0) < 0.5
    # обрезка до длины из файла
    path2 = build_path('L', [(0.0, 0.0), (100.0, 0.0)], 40.0)
    assert abs(path_length(path2) - 40.0) < 0.5


def test_bezier_path():
    # дуга Безье: контрольные точки в квадрате
    pts = [(0.0, 0.0), (50.0, 100.0), (100.0, 0.0)]
    path = build_path('B', pts, 1000.0)  # длина больше кривой — не растягиваем
    assert len(path) > 10
    natural = path_length(path)
    assert 100 < natural < 300
    # путь не выходит за пределы контрольных точек
    assert path[:, 0].min() >= -1 and path[:, 0].max() <= 101
    # обрезка кривой до меньшей длины
    cut = build_path('B', pts, 50.0)
    assert abs(path_length(cut) - 50.0) < 1.0


def test_point_at_distance():
    path = build_path('L', [(0.0, 0.0), (100.0, 0.0)], 100.0)
    x, y = point_at_distance(path, 50.0)
    assert abs(x - 50.0) < 1.0 and abs(y) < 0.5
    x2, y2 = point_at_distance(path, 500.0)  # за пределами — конец пути
    assert abs(x2 - 100.0) < 1.0


def test_real_map_sliders():
    """На реальной карте: у всех слайдеров появляется end_time."""
    import glob
    files = glob.glob(r'./beatmaps/_ref/*.osu')
    if not files:
        return  # карта не скачана — пропускаем
    bm = Beatmap.from_file(files[0])
    sliders = [o for o in bm.hit_objects if o.kind == 'slider']
    assert sliders, 'в карте должны быть слайдеры'
    assert all(o.end_time is not None for o in sliders)
    assert all(o.end_time > o.time for o in sliders)


def test_slider_progress_covers_length_at_end():
    """За время слайдера курсор обязан пройти РОВНО его длину (защита от ×1000)."""
    bm = Beatmap.from_text(SAMPLE)
    sliders = [o for o in bm.hit_objects if o.kind == 'slider']
    for sl in sliders:
        velocity_ms = bm.slider_velocity(sl.time)      # osu-px/мс
        duration_sec = (sl.end_time - sl.time) / 1000.0
        progress_px = duration_sec * velocity_ms * 1000.0   # как считает player.py
        assert abs(progress_px - sl.length) < 1e-6, (
            'прогресс за слайдер должен равняться его длине: %.3f vs %.3f'
            % (progress_px, sl.length))
