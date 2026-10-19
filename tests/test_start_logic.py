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


def make_player(first_ms: int) -> MapPlayer:
    bm = Beatmap.from_text(TEMPLATE.format(first=first_ms, second=first_ms + 1000))
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
