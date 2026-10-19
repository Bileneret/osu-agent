"""Подготовка прогона: выйти из провала, включить No Fail, запустить карту."""
import io
import sys
import time

sys.path.insert(0, r'.')
from osu_agent import input_driver as idrv
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOX_CROSS = (95, 940, 160, 1010)
BOX_BACK = (30, 1000, 360, 1080)


def grab():
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    return Image.frombytes('RGB', shot.size, shot.rgb)


def white(img):
    return sum(1 for r, g, b in img.crop(BOX_CROSS).getdata() if r > 190 and g > 190 and b > 190)


def pink(img):
    return sum(1 for r, g, b in img.crop(BOX_BACK).getdata() if r > 180 and g < 90 and b > 100)


hwnd = idrv.find_window()
idrv.activate(hwnd)

state = 'игра' if white(grab()) > 200 else ('songselect' if pink(grab()) > 5000 else 'прочее')
print('состояние:', state)

if state != 'songselect':
    # экран провала или иное — жмём Esc, чтобы вернуться
    idrv.key(27)
    time.sleep(1.5)
    if white(grab()) > 200:
        # пауза — выходим через клик по «Выйти» на паузе (третья кнопка)
        idrv.click(960, 654)
        time.sleep(2.0)
    state = 'songselect' if pink(grab()) > 5000 else 'прочее'
    print('после выхода:', state)

# включаем No Fail: кнопка «Моды»
idrv.click(475, 1043)
time.sleep(1.2)
print('панель модов:', idrv.shot('86_mods'))

# No Fail — по прошлому опыту на (588, 420); проверим по скрину после
idrv.click(588, 420)
time.sleep(0.8)
idrv.key(27)  # закрыть панель
time.sleep(1.0)
print('после мода:', idrv.shot('86_after_mod'))

# запуск
idrv.click(1810, 1005)
t0 = time.perf_counter()
ok = False
while time.perf_counter() - t0 < 25:
    if white(grab()) > 200:
        print('карта стартовала через %.2f c' % (time.perf_counter() - t0))
        ok = True
        break
    time.sleep(0.05)
if not ok:
    print('карта не стартовала')
    idrv.shot('86_stuck')
sys.exit(0 if ok else 2)
