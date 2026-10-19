"""Последняя попытка: длинный клик (0.6 с) и двойной клик по кнопке «играть»."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def find_purple(img, y0=500, y1=700):
    crop = img.crop((0, y0, img.width, y1))
    px = crop.load()
    pts = []
    for y in range(0, crop.height, 2):
        for x in range(0, crop.width, 2):
            r, g, b = px[x, y]
            if b > 200 and 90 < r < 170 and g < 90:
                pts.append((x, y + y0))
    if len(pts) < 50:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def hold(cx, cy, ms):
    idrv.move_absolute(cx, cy)
    time.sleep(0.3)
    inp = idrv.INPUT(type=idrv.INPUT_MOUSE)
    inp.union.mi = idrv.MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=idrv.MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=None)
    idrv._send(inp)
    time.sleep(ms / 1000.0)
    inp.union.mi = idrv.MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=idrv.MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=None)
    idrv._send(inp)


hwnd = idrv.find_window()
idrv.activate(hwnd)
time.sleep(0.3)

# вернуть меню в исходный ряд (Enter переключает)
idrv.key(0x0D)
time.sleep(0.8)
idrv.key(0x5A)
time.sleep(0.4)

box = find_purple(grab())
print('кнопка:', box)
if not box:
    sys.exit(1)
cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2

print('длинный клик 600 мс в', cx, cy)
hold(cx, cy, 600)
time.sleep(2.5)
print('снимок A:', idrv.shot('83_hold'))

# если всё ещё меню — двойной клик
box = find_purple(grab())
if box:
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    print('двойной клик в', cx, cy)
    idrv.move_absolute(cx, cy)
    time.sleep(0.25)
    idrv.click(cx, cy)
    time.sleep(0.1)
    idrv.click(cx, cy)
    time.sleep(2.5)
    print('снимок B:', idrv.shot('83_double'))
