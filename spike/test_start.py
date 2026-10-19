"""Быстрый тест старта: сыграть только первый объект карты (совместимая обёртка).

Теперь это `run_map.py --test`: играет первый объект и снимает экран паузы,
где видна «Точность» текущей попытки (100.00% = нота взята с 300).

    python spike/test_start.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_map import main  # noqa: E402

DEFAULTS = [
    '--osu', str(Path(__file__).resolve().parents[1] / 'beatmaps/_ref/pearto.osu'),
    '--audio', str(Path(__file__).resolve().parents[1] / 'beatmaps/_ref/beach_bunny.mp3'),
    '--test',
    '--shot', str(Path(__file__).resolve().parents[1] / 'spike/shots/test_first'),
]

if __name__ == '__main__':
    sys.exit(main(DEFAULTS + sys.argv[1:]))
