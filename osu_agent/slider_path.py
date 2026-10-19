"""Геометрия слайдеров: построение пути по кривой и расчёт длительности.

В `.osu` слайдер задан: координата головы, тип кривой и контрольные точки:
- `L` — линейный (прямые между точками);
- `B` — Безье (сегменты разделяются ПОВТОРЯЮЩИМИСЯ точками, как в osu!);
- `C` — Catmull-Rom (центрипетальный, так считает lazer);
- `P` — Perfect Curve (в lazer — комбинация дуг/линий); здесь аппроксимируется
  как Безье по контрольным точкам (для ведения достаточно, помечено).

Путь нормируется по длине из файла карты (`length`): osu! обрезает кривую до неё.
"""

from __future__ import annotations

import math

import numpy as np

Point = tuple[float, float]


def _bezier(points: np.ndarray, steps: int) -> np.ndarray:
    """Кривая Безье произвольного порядка (алгоритм де Кастельжо по параметру)."""
    n = len(points)
    if n == 1:
        return points.copy()
    t = np.linspace(0.0, 1.0, steps)[:, None]
    # de Casteljau
    work = np.repeat(points[None, :, :], steps, axis=0)
    for k in range(1, n):
        work = work[:, :-1, :] * (1 - t[:, None, :]) + work[:, 1:, :] * t[:, None, :]
    return work[:, 0, :]


def _catmull_rom(points: np.ndarray, steps_per_seg: int) -> np.ndarray:
    """Центрипетальный Catmull-Rom (реализация lazer близка к этому)."""
    if len(points) < 3:
        return _bezier(points, max(2, steps_per_seg * max(1, len(points) - 1)))
    pts = np.vstack([points[0], points, points[-1]])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        # центрипетальные параметры
        def tj(ti, pa, pb):
            d = np.linalg.norm(pb - pa)
            return ti + d ** 0.5
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        if t2 - t1 < 1e-6:
            seg = np.linspace(p1, p2, steps_per_seg)
        else:
            ts = np.linspace(t1, t2, steps_per_seg)[:, None]
            a1 = (t1 - ts) / (t1 - t0) * p0 + (ts - t0) / (t1 - t0) * p1
            a2 = (t2 - ts) / (t2 - t1) * p1 + (ts - t1) / (t2 - t1) * p2
            a3 = (t3 - ts) / (t3 - t2) * p2 + (ts - t2) / (t3 - t2) * p3
            b1 = (t2 - ts) / (t2 - t0) * a1 + (ts - t0) / (t2 - t0) * a2
            b2 = (t3 - ts) / (t3 - t1) * a2 + (ts - t1) / (t3 - t1) * a3
            seg = (t2 - ts) / (t2 - t1) * b1 + (ts - t1) / (t2 - t1) * b2
        out.append(seg if i == 1 else seg[1:])
    return np.vstack(out)


def _circle_arc(a: np.ndarray, b: np.ndarray, c: np.ndarray, expected_length: float,
                samples_per_10px: float = 2.0) -> np.ndarray | None:
    """Дуга описанной окружности через три точки (истинная геометрия Perfect Curve).

    Возвращает массив точек или None, если точки коллинеарны (тогда — прямая).
    """
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(c[0]), float(c[1])
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    if r < 1e-6:
        return None

    theta_a = math.atan2(ay - uy, ax - ux)
    theta_b = math.atan2(by - uy, bx - ux)
    theta_c = math.atan2(cy - uy, cx - ux)

    def norm(x: float) -> float:
        while x < 0:
            x += 2 * math.pi
        while x >= 2 * math.pi:
            x -= 2 * math.pi
        return x

    # выбираем направление обхода, проходящее через B
    ccw_span = norm(theta_c - theta_a)
    ccw_b = norm(theta_b - theta_a)
    if ccw_b <= ccw_span:
        span = ccw_span
        direction = 1.0
    else:
        span = ccw_span - 2 * math.pi  # отрицательное — по часовой
        direction = -1.0

    arc_len = abs(span) * r
    steps = max(6, int(arc_len / 10.0 * samples_per_10px))
    angles = theta_a + (span if direction > 0 else span) * np.linspace(0.0, 1.0, steps)
    return np.stack([ux + r * np.cos(angles), uy + r * np.sin(angles)], axis=1)


def _perfect_curve(points: np.ndarray, expected_length: float,
                   samples_per_10px: float = 2.0) -> np.ndarray:
    """Perfect Curve: 3 точки — дуга описанной окружности (истинная геометрия lazer).

    Для >3 точек (редкость) — аппроксимация Безье: в lazer PerfectCurve строится
    как последовательность дуг/прямых, здесь этим случаем пренебрегаем.
    """
    if len(points) == 3:
        arc = _circle_arc(points[0], points[1], points[2], expected_length, samples_per_10px)
        if arc is not None and len(arc) > 1:
            return arc
        return np.linspace(points[0], points[-1], max(2, int(expected_length / 5.0) + 1))
    return _bezier(points, max(2, int(expected_length / 5.0)))


def build_path(curve_type: str | None, points: list[Point], expected_length: float,
               samples_per_10px: float = 2.0) -> np.ndarray:
    """Построить путь слайдера: массив точек (N×2) от головы до хвоста.

    `expected_length` — длина из `.osu` (в osu!-пикселях); путь обрезается
    до неё, как это делает игра.
    """
    pts = [tuple(map(float, p)) for p in points]
    if not pts:
        return np.zeros((1, 2), dtype=np.float64)

    all_pts = np.array(pts, dtype=np.float64)
    ct = (curve_type or 'L').upper()

    if ct == 'L' or len(all_pts) == 1:
        segments = [np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / 5.0) + 1))
                    for a, b in zip(all_pts, all_pts[1:])] or [all_pts]
        path = np.vstack(segments)
    elif ct == 'C':
        path = _catmull_rom(all_pts, max(8, int(expected_length / 5.0)))
    elif ct == 'P':
        path = _perfect_curve(all_pts, expected_length, samples_per_10px)
    else:  # 'B' — Безье (сегменты разделяются повторяющимися точками)
        segments: list[np.ndarray] = []
        start = 0
        for i in range(1, len(all_pts)):
            if np.allclose(all_pts[i], all_pts[i - 1]):
                seg = all_pts[start:i]
                if len(seg) >= 2:
                    segments.append(seg)
                start = i
        seg = all_pts[start:]
        if len(seg) >= 2:
            segments.append(seg)
        if not segments:
            segments = [all_pts]
        parts = [_bezier(s, max(2, int(expected_length / 5.0))) for s in segments]
        path = np.vstack(parts)

    # нормировка длины: если кривая длиннее — обрезаем до expected_length.
    # (Если короче — путь оставляем как есть: искажать геометрию растяжением нельзя,
    #  длительность слайдера всё равно считается по length из файла карты.)
    if expected_length > 0:
        seg_vec = np.diff(path, axis=0)
        seg_len = np.linalg.norm(seg_vec, axis=1)
        cum = np.concatenate(([0.0], np.cumsum(seg_len)))
        total = cum[-1]
        if total > expected_length:
            idx = int(np.searchsorted(cum, expected_length))
            if idx >= 1:
                over = (expected_length - cum[idx - 1]) / max(seg_len[idx - 1], 1e-9)
                cut = path[:idx]
                last = path[idx - 1] + seg_vec[idx - 1] * over
                path = np.vstack([cut, last])
    return path


def path_length(path: np.ndarray) -> float:
    if len(path) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())


def point_at_distance(path: np.ndarray, distance: float) -> Point:
    """Точка на пути на заданном расстоянии от начала (для ведения)."""
    if len(path) == 1:
        return float(path[0][0]), float(path[0][1])
    seg_vec = np.diff(path, axis=0)
    seg_len = np.linalg.norm(seg_vec, axis=1)
    cum = np.concatenate(([0.0], np.cumsum(seg_len)))
    total = cum[-1]
    d = min(max(distance, 0.0), total)
    idx = int(np.searchsorted(cum, d))
    if idx <= 0:
        return float(path[0][0]), float(path[0][1])
    if idx >= len(path):
        return float(path[-1][0]), float(path[-1][1])
    over = (d - cum[idx - 1]) / max(seg_len[idx - 1], 1e-9)
    p = path[idx - 1] + seg_vec[idx - 1] * over
    return float(p[0]), float(p[1])
