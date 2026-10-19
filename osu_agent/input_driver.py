"""Синтетический ввод и захват экрана — «руки и глаза» спайка.

Пока это минимальный слой для проверки дня 1: доходят ли синтетические
события (движение мыши, клик, клавиши) до osu!lazer. Всё — через штатный
SendInput ОС, без модификации игры.

CLI:
    python -m osu_agent.input_driver activate
    python -m osu_agent.input_driver cursor
    python -m osu_agent.input_driver move 960 540
    python -m osu_agent.input_driver click 960 540
    python -m osu_agent.input_driver key 27            # VK-код (27 = Esc)
    python -m osu_agent.input_driver shot имя_снимка
"""

from __future__ import annotations

import argparse
import ctypes
import math
import queue
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

# --- DPI: работаем в физических пикселях (у пользователя масштаб 125%) ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Точный системный таймер: без него квант планировщика Windows — 15.6 мс,
# что полностью нивелирует микросекундное планирование ударов.
ctypes.windll.winmm.timeBeginPeriod(1)

# --- SendInput ---
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _send(inp: INPUT) -> None:
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError(f"SendInput вернул {sent}, ошибка {kernel32.GetLastError()}")


def virtual_screen() -> tuple[int, int, int, int]:
    """Границы виртуального рабочего стола в физических пикселях."""
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def move_absolute(x: int, y: int) -> None:
    """Переместить курсор в абсолютную точку экрана (физические пиксели)."""
    vx, vy, vw, vh = virtual_screen()
    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(
        dx=nx, dy=ny, mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
        time=0, dwExtraInfo=None,
    )
    _send(inp)


def click(x: int | None = None, y: int | None = None, button: str = "left", settle: float = 0.06) -> None:
    """Клик мышью (при необходимости — с предварительным перемещением)."""
    if x is not None and y is not None:
        move_absolute(x, y)
        time.sleep(settle)
    down = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
    for flag in (down, up):
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=None)
        _send(inp)
        time.sleep(0.012)


def key_down(vk: int) -> None:
    """Нажать клавишу (событие KeyDown — именно его судит игра)."""
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
    _send(inp)


def key_up(vk: int) -> None:
    """Отпустить клавишу."""
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
    _send(inp)


TAP_HOLD_MS = 25

# --- неблокирующее отпускание клавиш ---
# tap() не спит: KeyDown уходит немедленно, а KeyUp ставится в очередь и
# отпускается отдельным потоком-релизером. На стримах (интервал 62–75 мс)
# синхронный sleep(25 мс) парализовал бы планировщик и движение курсора.
_release_queue: "queue.PriorityQueue[tuple[float, int]]" = queue.PriorityQueue()
_release_thread: threading.Thread | None = None
_release_lock = threading.Lock()


def _ensure_releaser() -> None:
    global _release_thread
    with _release_lock:
        if _release_thread is None or not _release_thread.is_alive():
            _release_thread = threading.Thread(target=_release_worker, daemon=True, name="key-releaser")
            _release_thread.start()


def _release_worker() -> None:
    while True:
        when, vk = _release_queue.get()
        now = time.perf_counter()
        if when > now:
            time.sleep(when - now)
        try:
            key_up(vk)
        except OSError:
            pass


def release_all() -> None:
    """Отпустить все запланированные клавиши немедленно (аварийный сброс)."""
    while not _release_queue.empty():
        try:
            _release_queue.get_nowait()
        except queue.Empty:
            break
    for vk in (0x5A, 0x58):  # Z, X
        try:
            key_up(vk)
        except OSError:
            pass


def tap(vk: int, hold_ms: float = TAP_HOLD_MS) -> None:
    """Тап без блокировки: KeyDown сейчас, KeyUp — через hold_ms (в фоне)."""
    _ensure_releaser()
    key_down(vk)
    _release_queue.put((time.perf_counter() + hold_ms / 1000.0, vk))


_next_tap_vk = 0x5A  # начинаем с Z


def tap_alternate(hold_ms: float = TAP_HOLD_MS) -> int:
    """Тап с чередованием Z ↔ X (для стримов одной рукой невозможно, нужны обе).

    Возвращает использованную клавишу.
    """
    global _next_tap_vk
    vk = _next_tap_vk
    _next_tap_vk = 0x58 if vk == 0x5A else 0x5A
    tap(vk, hold_ms)
    return vk


def key(vk: int) -> None:
    """Совместимость: тап клавишей (KeyDown + KeyUp в фоне)."""
    tap(vk)


def type_text(text: str) -> None:
    """Ввод текста через KEYEVENTF_UNICODE — не зависит от раскладки клавиатуры."""
    for ch in text:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.union.ki = KEYBDINPUT(wVk=0, wScan=ord(ch), dwFlags=flags, time=0, dwExtraInfo=None)
            _send(inp)
            time.sleep(0.02)


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> None:
    """Прокрутка колесом: clicks > 0 — вниз, < 0 — вверх."""
    if x is not None and y is not None:
        move_absolute(x, y)
        time.sleep(0.05)
    step = WHEEL_DELTA if clicks > 0 else -WHEEL_DELTA
    for _ in range(abs(clicks)):
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=step & 0xFFFFFFFF, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None)
        _send(inp)
        time.sleep(0.05)


def drag(x1: int, y1: int, x2: int, y2: int, steps: int = 24) -> None:
    """Перетаскивание: нажать в (x1,y1), плавно провести, отпустить в (x2,y2)."""
    move_absolute(x1, y1)
    time.sleep(0.12)
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=None)
    _send(inp)
    time.sleep(0.12)
    for i in range(1, steps + 1):
        x = int(x1 + (x2 - x1) * i / steps)
        y = int(y1 + (y2 - y1) * i / steps)
        move_absolute(x, y)
        time.sleep(0.015)
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=None)
    _send(inp)


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


# --- перевод координат osu!-поля (512×384) в экранные пиксели ---
# Источник истины — код lazer: osu.Game.Rulesets.Osu/UI/OsuPlayfieldAdjustmentContainer.cs
#   playfield_size_adjust = 0.8  (поле занимает 80% от логического игрового пространства)
#   логическое пространство 1024×768 вписывается в экран с сохранением аспекта (fit)
#   PlayfieldShift сдвигает поле вниз на 8 osu-единиц
# При 1920×1080: scale = 2.25, offset = (384, 126). (Проверено измерением по скриншотам.)
OSU_BASE = (512.0, 384.0)
LOGICAL_GAME = (1024.0, 768.0)
PLAYFIELD_SIZE_ADJUST = 0.8
PLAYFIELD_SHIFT_OSU = 8.0


def playfield_transform(screen_w: int | None = None, screen_h: int | None = None):
    """Вернуть (scale, offset_x, offset_y) для перевода osu!-координат в пиксели."""
    if screen_w is None or screen_h is None:
        _, _, screen_w, screen_h = virtual_screen()
    fit = min(screen_w / LOGICAL_GAME[0], screen_h / LOGICAL_GAME[1])
    scale = PLAYFIELD_SIZE_ADJUST * fit * LOGICAL_GAME[1] / OSU_BASE[1]  # = 1.6 * fit
    offset_x = (screen_w - OSU_BASE[0] * scale) / 2.0
    offset_y = (screen_h - OSU_BASE[1] * scale) / 2.0 + PLAYFIELD_SHIFT_OSU * scale
    return scale, offset_x, offset_y


def osu_to_screen(x: float, y: float) -> tuple[int, int]:
    """Перевести координаты ноты из `.osu` (0..512, 0..384) в экранные пиксели."""
    scale, ox, oy = playfield_transform()
    return int(round(ox + x * scale)), int(round(oy + y * scale))


# --- окно игры ---

def find_window(prefix: str = "osu!") -> int:
    """Найти окно игры: заголовок может меняться (в игре — 'osu! - карта ...')."""
    found: list[int] = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value.startswith(prefix) and user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found[0] if found else 0


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def activate(hwnd: int) -> bool:
    """Поднять окно игры на передний план (с обходом защиты SetForegroundWindow)."""
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    VK_MENU = 0x12
    user32.keybd_event(VK_MENU, 0, 0, 0)
    ok = bool(user32.SetForegroundWindow(hwnd))
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.25)
    return ok and int(user32.GetForegroundWindow()) == hwnd


# --- захват экрана ---

def shot(name: str, out_dir: str = "spike/shots") -> Path:
    """Скриншот всего экрана в spike/shots/<name>.png."""
    import mss
    import mss.tools

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / (name if name.endswith(".png") else name + ".png")
    with mss.mss() as sct:
        img = sct.grab(sct.monitors[1])
        mss.tools.to_png(img.rgb, img.size, output=str(path))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Инструмент игровой сессии (ввод/скриншоты)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("activate")
    sub.add_parser("cursor")
    sub.add_parser("fg")
    p_move = sub.add_parser("move"); p_move.add_argument("x", type=int); p_move.add_argument("y", type=int)
    p_click = sub.add_parser("click"); p_click.add_argument("x", type=int); p_click.add_argument("y", type=int)
    p_key = sub.add_parser("key"); p_key.add_argument("vk", type=int)
    p_type = sub.add_parser("type"); p_type.add_argument("text")
    p_shot = sub.add_parser("shot"); p_shot.add_argument("name")
    p_scroll = sub.add_parser("scroll"); p_scroll.add_argument("clicks", type=int); p_scroll.add_argument("--x", type=int); p_scroll.add_argument("--y", type=int)
    p_drag = sub.add_parser("drag"); p_drag.add_argument("x1", type=int); p_drag.add_argument("y1", type=int); p_drag.add_argument("x2", type=int); p_drag.add_argument("y2", type=int)
    p_hold = sub.add_parser("keydown"); p_hold.add_argument("vk", type=int)
    p_up = sub.add_parser("keyup"); p_up.add_argument("vk", type=int)

    args = parser.parse_args(argv)

    if args.cmd == "activate":
        hwnd = find_window()
        if not hwnd:
            print("Окно игры не найдено")
            return 1
        ok = activate(hwnd)
        print("активировано:", ok, "| foreground:", foreground_title())
        return 0 if ok else 2
    if args.cmd == "cursor":
        print(*cursor_pos())
        return 0
    if args.cmd == "fg":
        print(foreground_title())
        return 0
    if args.cmd == "move":
        move_absolute(args.x, args.y)
        time.sleep(0.05)
        print("курсор:", *cursor_pos())
        return 0
    if args.cmd == "click":
        click(args.x, args.y)
        print("клик в", args.x, args.y, "| курсор:", *cursor_pos())
        return 0
    if args.cmd == "key":
        key(args.vk)
        print("клавиша", args.vk)
        return 0
    if args.cmd == "type":
        type_text(args.text)
        print("введено:", args.text)
        return 0
    if args.cmd == "scroll":
        scroll(args.clicks, args.x, args.y)
        print("прокрутка:", args.clicks)
        return 0
    if args.cmd == "drag":
        drag(args.x1, args.y1, args.x2, args.y2)
        print("перетаскивание:", args.x1, args.y1, "->", args.x2, args.y2)
        return 0
    if args.cmd == "keydown":
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki = KEYBDINPUT(wVk=args.vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
        _send(inp)
        return 0
    if args.cmd == "keyup":
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki = KEYBDINPUT(wVk=args.vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
        _send(inp)
        return 0
    if args.cmd == "shot":
        path = shot(args.name)
        print("снимок:", path)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
