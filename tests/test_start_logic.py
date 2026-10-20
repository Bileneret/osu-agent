"""Тесты логики запуска: выбор стратегии старта, свободная клавиша, упреждение."""

import numpy as np

from osu_agent import input_driver as idrv
from osu_agent.beatmap import Beatmap
from osu_agent.player import MapPlayer

REF = np.zeros(48000 * 2, dtype=np.float32)

TEMPLATE = """osu file format v14

[General]
AudioFilename: audio.mp3
AudioLeadIn: 0
Mode: 0

[Metadata]
Title:Test
Artist:Test
Creator:Test
Version:Test
BeatmapID:1
BeatmapSetID:2

[Difficulty]
OverallDifficulty:2
ApproachRate:3
CircleSize:2
SliderMultiplier:0.8
SliderTickRate:1

[TimingPoints]
{first},400,4,2,1,60,1,0

[HitObjects]
100,100,{first},1,0
200,100,{second},1,0
"""


def make_player(first_ms: int, gap_ms: int = 1000) -> MapPlayer:
    bm = Beatmap.from_text(TEMPLATE.format(first=first_ms, second=first_ms + gap_ms))
    return MapPlayer(bm, REF, 'none', s_offset=0.10)


def test_predicted_start_needed_for_early_first_note():
    """Первая нота 140 мс: тап нужен раньше, чем звук доступен детектору."""
    assert make_player(140).needs_predicted_start() is True


def test_direct_start_for_regular_first_note():
    """Первая нота 2 с: детект онсета успевает задолго до неё."""
    assert make_player(2000).needs_predicted_start() is False


def test_predicted_threshold_boundary():
    p = make_player(1499)
    assert p.needs_predicted_start(threshold_sec=1.5) is True
    p2 = make_player(1500)
    assert p2.needs_predicted_start(threshold_sec=1.5) is False


def test_move_lead_bounds():
    """Время перелёта курсора: не меньше 30 мс и не больше 250 мс."""
    assert MapPlayer.move_lead_sec(0.0) == 0.030
    assert MapPlayer.move_lead_sec(10000.0) == 0.250
    assert abs(MapPlayer.move_lead_sec(500.0) - 0.200) < 1e-9


def test_free_key_skips_pressed_key():
    """Нажатая клавиша (KeyUp ещё не ушёл) не выбирается для следующего удара."""
    idrv._mark_released(idrv.VK_Z)
    idrv._mark_released(idrv.VK_X)
    assert idrv.free_key() == idrv.VK_Z
    idrv._mark_pressed(idrv.VK_Z)
    assert idrv.key_is_active(idrv.VK_Z)
    assert idrv.free_key() == idrv.VK_X
    idrv._mark_released(idrv.VK_Z)
    assert not idrv.key_is_active(idrv.VK_Z)
    assert idrv.free_key() == idrv.VK_Z


def test_free_key_falls_back_when_all_pressed():
    idrv._mark_pressed(idrv.VK_Z)
    idrv._mark_pressed(idrv.VK_X)
    assert idrv.free_key(wait=0.01) == idrv.VK_Z
    idrv._mark_released(idrv.VK_Z)
    idrv._mark_released(idrv.VK_X)


def test_tail_hold_shortens_with_next_object():
    """Удержание хвоста слайдера сокращается, когда следующий объект близко."""
    assert MapPlayer.tail_hold_sec_for(None, 0.015) == 0.015
    assert abs(MapPlayer.tail_hold_sec_for(0.0475, 0.015) - 0.011875) < 1e-9
    assert MapPlayer.tail_hold_sec_for(0.001, 0.015) == 0.003      # нижняя граница
    assert MapPlayer.tail_hold_sec_for(0.0475, 0.005) == 0.005     # плотный режим


def test_auto_tune_dense_and_normal():
    """Плотная карта (49 мс) включает плотный режим; обычная — нет."""
    dense = make_player(140, gap_ms=49)
    dense.auto_tune()
    assert dense.dense is True
    assert dense.min_gap_ms == 49
    assert dense.tap_hold_ms == 18.0
    assert dense.lead_speed_px_ms == 6.0

    normal = make_player(140, gap_ms=200)
    normal.auto_tune()
    assert normal.dense is False
    assert normal.tap_hold_ms == 25.0
    assert normal.lead_speed_px_ms == 2.5


def test_relocation_is_smooth_not_a_jump():
    """Релокация подмешивает ошибку с коэффициентом, а не перезаписывает якорь."""
    import threading
    p = make_player(140)
    p.t_anchor, p.t_end_pos = 100.0, 0.0
    p._reloc_lock = threading.Lock()
    p._reloc_result = (1.05, 0.9, 101.0)   # ошибка +0.05 с
    p.apply_relocation()
    expected = 100.0 - 0.05 * 0.15
    assert abs(p.t_anchor - expected) < 1e-9
    assert p.t_anchor != 101.0 - 1.05       # не жёсткая замена
