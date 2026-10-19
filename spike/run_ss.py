"""Прогон карты Beach Bunny [pearto's Easy] (совместимая обёртка).

Раньше этот скрипт был самостоятельным; теперь вся логика — в параметризованном
`run_map.py`. Оставлен для совместимости с прежними командами.

    python spike/run_ss.py [--delta 3.49] [--test]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_map import main  # noqa: E402

DEFAULTS = [
    '--osu', str(Path(__file__).resolve().parents[1] / 'beatmaps/_ref/pearto.osu'),
    '--audio', str(Path(__file__).resolve().parents[1] / 'beatmaps/_ref/beach_bunny.mp3'),
    '--shot', str(Path(__file__).resolve().parents[1] / 'spike/shots/run_pearto'),
]

if __name__ == '__main__':
    sys.exit(main(DEFAULTS + sys.argv[1:]))
