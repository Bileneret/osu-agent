"""osu!-агент: инженерный полигон точного тайминга и ввода (офлайн, research).

Слои проекта:
- beatmap  — чтение карт `.osu` (парсинг нот, таймингов, слайдеров)
- (далее)  — аудио-клок, планировщик ударов, ввод, кинематика, метрики
"""

from .beatmap import Beatmap, HitObject, TimingPoint

__all__ = ["Beatmap", "HitObject", "TimingPoint"]
__version__ = "0.1.0"
