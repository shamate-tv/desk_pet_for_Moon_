# -*- coding: utf-8 -*-
"""Moon 桌宠 · Bongo Cat 版

  打字 -> 左右爪交替下砸 + 整体(以底边为锚)纵向压缩, 空闲 -> 随机眨眼, 鼠标点击 -> 双爪同砸。

素材: assets/bg.png(场景板) / paw_l.png / paw_r.png(两只手套爪) / eyes_closed.png(闭眼) / keys.json(键位)
      由 tools/bongo_bg.py 从画师分好的 art/ 图层拼出(bongo_keys.py 生成键位表)。
运行: python pet/main.py            正常启动
      python pet/main.py --demo     演示模式(自动模拟打字, 不用真的敲键盘)
      python pet/main.py --selftest build/selftest_bongo.png

热键: Ctrl+Alt+P 鼠标穿透开关    Ctrl+Alt+H 显示/隐藏
"""
import os
import sys
import json
import math
import random
import time

from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import (QImage, QPixmap, QPainter, QAction, QActionGroup, QIcon, QColor)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
                               QMessageBox)

# ----------------------------------------------------------------------------- 常量
VERSION = "2.1.0"                         # 发版时改这里(打包脚本会读它写进 exe 属性)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR
SKINS_DIR = os.path.join(RES_DIR, "skins")
CONFIG = os.path.join(BASE_DIR, "config.json")
DEFAULT_SKIN = "moon"

# 下面这些都由 load_skin() 按皮肤填
SKIN_NAME = ""
SKIN = {}
SPRITE_W, SPRITE_H = 0, 0
PAW_BOX = {"l": (0, 0, 0, 0), "r": (0, 0, 0, 0)}
PAW_W, PAW_H = 0, 0
EYE_BOX = (0, 0, 0, 0)
KEYS = {}
LIFT_PX = 30.0
HOVER_KEEP = 1.5
FOLLOW_MOUSE = True
PRESS_KEYS = True
MOUSE_DX = (-210.0, 40.0)
MOUSE_DY = (-40.0, 45.0)

PAW_SQUASH = 0.16        # 砸到桌面瞬间的纵向压扁比例
PAW_WIDEN = 0.08
FOLLOW_K = 70.0          # 爪子"滑向目标"的弹簧刚度(越大跟得越紧)
FOLLOW_C = 13.0
BODY_SQUASH = 0.020      # 整体纵向压缩(锚在底边 => 桌子几乎不动, 头肩下沉)
BODY_WIDEN = 0.006
K_HIT, C_HIT = 900.0, 40.0    # 爪子弹簧参数(冲量驱动, 自然回弹)
K_BODY, C_BODY = 620.0, 34.0
HOVER_K, HOVER_C = 150.0, 17.0    # 抬爪弹簧(软一点, 像手臂抬起)
IMPULSE, IMPULSE_BODY = 9.0, 7.0
BLINK_CLOSE, BLINK_HOLD, BLINK_OPEN = 0.05, 0.04, 0.075


# ----------------------------------------------------------------------------- 皮肤
def list_skins():
    """skins/ 下所有带 skin.json 的目录。"""
    try:
        return sorted(d for d in os.listdir(SKINS_DIR)
                      if not d.startswith("_")                       # _template 之类不进菜单
                      and os.path.isfile(os.path.join(SKINS_DIR, d, "skin.json")))
    except Exception:
        return []


def _alpha_box(pm, pad_l=6, pad_t=6, pad_r=0.12, pad_b=0.12):
    """从 alpha 通道算包围盒并留出余量(够下砸压扁/左右撑开用)。

    用 Qt 自带的 QRegion, 不引 numpy —— numpy 一旦被 import 就会被打进 exe(多 12MB)。
    没有它的话每加一个皮肤都要手填坐标; 想微调在 skin.json 里写 paw_boxes 覆盖即可。
    """
    from PySide6.QtGui import QBitmap, QRegion
    img = pm.toImage()
    w, h = img.width(), img.height()
    try:
        mask = img.createAlphaMask()                  # alpha > 128 转 1bit
        r = QRegion(QBitmap.fromImage(mask)).boundingRect()
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
    except Exception:
        return (0, 0, w, h)
    if x1 < x0 or y1 < y0:
        return (0, 0, w, h)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    return (max(0, int(x0 - pad_l)), max(0, int(y0 - pad_t)),
            min(w, int(x1 + pad_r * bw) + 1), min(h, int(y1 + pad_b * bh) + 1))


def skin_path(name, *parts):
    return os.path.join(SKINS_DIR, name, *parts)


def load_skin(name):
    """读 skins/<name>/skin.json 并填好所有全局量。素材缺失会抛异常。"""
    global SKIN_NAME, SKIN, SPRITE_W, SPRITE_H, PAW_BOX, PAW_W, PAW_H, EYE_BOX
    global KEYS, LIFT_PX, HOVER_KEEP, FOLLOW_MOUSE, PRESS_KEYS, MOUSE_DX, MOUSE_DY
    d = skin_path(name)
    if not os.path.isfile(os.path.join(d, "skin.json")):
        raise SystemExit("找不到皮肤: %s (%s 里没有 skin.json)" % (name, d))
    with open(os.path.join(d, "skin.json"), encoding="utf-8") as fh:
        SKIN = json.load(fh)
    SKIN_NAME = name

    base = QPixmap(os.path.join(d, "bg.png"))
    if base.isNull():
        raise SystemExit("皮肤 %s 缺 bg.png" % name)
    SPRITE_W, SPRITE_H = base.width(), base.height()

    paw_pm = {}
    for k in ("l", "r"):
        pm = QPixmap(os.path.join(d, "paw_%s.png" % k))
        if pm.isNull():
            raise SystemExit("皮肤 %s 缺 paw_%s.png" % (name, k))
        paw_pm[k] = pm
    boxes = SKIN.get("paw_boxes") or {}
    for k in ("l", "r"):
        PAW_BOX[k] = tuple(int(v) for v in boxes[k]) if k in boxes else _alpha_box(paw_pm[k])
    PAW_W = PAW_BOX["r"][2] - PAW_BOX["r"][0]
    PAW_H = PAW_BOX["r"][3] - PAW_BOX["r"][1]

    eyes = QPixmap(os.path.join(d, "eyes_closed.png"))
    EYE_BOX = tuple(int(v) for v in SKIN["eye_box"]) if SKIN.get("eye_box") else (
        _alpha_box(eyes, 0, 0, 0, 0) if not eyes.isNull() else (0, 0, 0, 0))

    LIFT_PX = float(SKIN.get("lift", 30.0))
    HOVER_KEEP = float(SKIN.get("hover_keep", 1.5))
    FOLLOW_MOUSE = bool(SKIN.get("follow_mouse", True))
    PRESS_KEYS = bool(SKIN.get("press_keys", True))
    MOUSE_DX = tuple(SKIN.get("mouse_dx", (-210.0, 40.0)))
    MOUSE_DY = tuple(SKIN.get("mouse_dy", (-40.0, 45.0)))

    KEYS = {}
    if PRESS_KEYS:
        try:
            with open(os.path.join(d, "keys.json"), encoding="utf-8") as fh:
                KEYS = json.load(fh)
        except Exception:
            KEYS = {}
    return SKIN

FPS = 60


# ----------------------------------------------------------------------------- 输入
class InputBridge(QObject):
    """把 pynput 的全局键鼠事件转到 Qt 主线程(信号跨线程自动排队)。"""
    key_press = Signal(str)
    clicked = Signal()
    hotkey = Signal(str)

    def __init__(self):
        super().__init__()
        self.mods = set()
        self.error = None

    def start(self):
        try:
            from pynput import keyboard, mouse
        except Exception as exc:
            self.error = "pynput 不可用: %s" % exc
            return False
        try:
            def on_press(key):
                # 普通字符键取 .char; 功能键取 .name。注意 Ctrl+字母 时 char 是控制字符
                ch = getattr(key, "char", None)
                if ch:
                    if len(ch) == 1 and ord(ch) < 32:
                        ch = chr(ord(ch) + 96)          #  -> 'p'
                    nm = ch.lower()
                else:
                    nm = (getattr(key, "name", None) or str(key).replace("Key.", "")).lower()
                if "ctrl" in nm:
                    self.mods.add("ctrl")
                elif "alt" in nm:
                    self.mods.add("alt")
                if self.mods >= {"ctrl", "alt"}:
                    if nm == "p":
                        self.hotkey.emit("passthrough")
                    elif nm == "h":
                        self.hotkey.emit("toggle_show")
                # 只把按键名传给动画用来选键位, 不记录/不上传
                self.key_press.emit(nm)

            def on_release(key):
                name = getattr(key, "name", None) or str(key).lstrip("Key.")
                if "ctrl" in name:
                    self.mods.discard("ctrl")
                elif "alt" in name:
                    self.mods.discard("alt")

            self._kb = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._ms = mouse.Listener(on_click=lambda *a: self.clicked.emit())
            for lsn in (self._kb, self._ms):
                lsn.daemon = True
                lsn.start()
            return True
        except Exception as exc:
            self.error = "全局钩子启动失败: %s" % exc
            return False


# ----------------------------------------------------------------------------- 桌宠
class Pet(QWidget):
    def __init__(self, skin=None, scale=None):
        super().__init__()
        self.cfg = self._load_cfg()
        # 显式指定的皮肤允许 _ 开头(方便试 _template); 菜单里仍然不显示它们
        self.skin = skin or self.cfg.get("skin") or DEFAULT_SKIN
        if not os.path.isfile(skin_path(self.skin, "skin.json")):
            self.skin = (list_skins() or [DEFAULT_SKIN])[0]
        load_skin(self.skin)
        self.scale = float(self.cfg.get("scale", scale if scale else SKIN.get("scale", 0.42)))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            (Qt.WindowStaysOnTopHint if self.cfg.get("on_top", True)
                             else Qt.WindowNoState))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Moon 桌宠 v%s" % VERSION)

        self._load_assets()
        self._resize()

        # 动画状态: 每只爪子一个弹簧 + 整体一个弹簧
        self.paw = {"l": 0.0, "r": 0.0}          # 落地冲击量(0~1.35), 驱动压扁
        self.paw_v = {"l": 0.0, "r": 0.0}
        self.up = {"l": 0.0, "r": 0.0}           # 抬爪量 0=贴桌 1=抬到最高
        self.up_v = {"l": 0.0, "r": 0.0}
        self.off = {"l": [0.0, 0.0], "r": [0.0, 0.0]}    # 相对原位的平移(去按键 / 跟鼠标)
        self.off_v = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
        self.tgt = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
        self.last_key_t = -99.0
        self.body = 0.0
        self.body_v = 0.0
        self.next_paw = "l"
        self.heat = 0.0
        self.blink_t0 = -9.0
        self.next_blink = time.monotonic() + random.uniform(2.5, 6.0)
        self.demo = False
        self.debug_keys = False
        self.drag_from = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.last = time.monotonic()
        self.timer.start(int(1000 / FPS))

        self.bridge = InputBridge()
        self.bridge.key_press.connect(self.on_key)
        self.bridge.clicked.connect(self.on_click)
        self.bridge.hotkey.connect(self.on_hotkey)
        self.input_ok = self.bridge.start()

        self._place()
        self._make_tray()

    # ---------------------------------------------------------------- 素材
    def _load_assets(self):
        """从当前皮肤目录读素材。load_skin() 已经把尺寸/包围盒/键位都算好了。"""
        d = skin_path(self.skin)
        self.pm_base = QPixmap(os.path.join(d, "bg.png"))
        self.pm_eyes = QPixmap(os.path.join(d, "eyes_closed.png"))
        self.paw_pm = {k: QPixmap(os.path.join(d, "paw_%s.png" % k)) for k in ("l", "r")}
        if any(pm.isNull() for pm in [self.pm_base] + list(self.paw_pm.values())):
            raise SystemExit("皮肤 %s 素材缺失" % self.skin)
        self.paw_bmp = {k: self.paw_pm[k].copy(*PAW_BOX[k]) for k in ("l", "r")}
        self.eyes_bmp = (self.pm_eyes.copy(*EYE_BOX) if not self.pm_eyes.isNull()
                         and EYE_BOX[2] > EYE_BOX[0] else QPixmap())
        self.tray_icon = self._make_icon()

    def switch_skin(self, name):
        """运行时换皮肤: 重载素材 + 重新定位。"""
        if name == self.skin or name not in list_skins():
            return
        load_skin(name)
        self.skin = name
        self._load_assets()
        self._resize()
        self.tgt = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
        self.off = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
        for k in ("l", "r"):
            self.off_v[k] = [0.0, 0.0]
        self.cfg["skin"] = name
        self.save_cfg()
        self.show()
        self.update()

    def _reset_pos(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 30, scr.bottom() - self.height() + 6)
        self.save_cfg()

    def _make_icon(self):
        head = self.pm_base.copy(430, 60, 620, 620)
        head = head.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QPixmap(64, 64)
        icon.fill(Qt.transparent)
        pr = QPainter(icon)
        pr.setRenderHint(QPainter.Antialiasing)
        pr.setBrush(QColor(32, 30, 40))
        pr.setPen(Qt.NoPen)
        pr.drawEllipse(0, 0, 64, 64)
        pr.drawPixmap(0, 0, head)
        pr.end()
        return QIcon(icon)

    # ---------------------------------------------------------------- 窗口
    def _resize(self):
        self.setFixedSize(int(SPRITE_W * self.scale), int(SPRITE_H * self.scale))

    def _place(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            x = scr.right() - self.width() - 30
            y = scr.bottom() - self.height() + 6
        self.move(int(x), int(y))
        self._clamp()

    def _clamp(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x = min(max(self.x(), scr.left() - self.width() // 3), scr.right() - self.width() // 3)
        y = min(max(self.y(), scr.top() - 10), scr.bottom() - 20)
        self.move(int(x), int(y))

    # ---------------------------------------------------------------- 交互
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.drag_from = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self.drag_from is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self.drag_from)
            ev.accept()

    def mouseReleaseEvent(self, _ev):
        self.drag_from = None

    def contextMenuEvent(self, ev):
        self.menu.exec(ev.globalPos())

    def keys_pos(self, ch):
        """取某个键在底图上的中心坐标。"""
        return KEYS.get(ch) or KEYS.get(ch.lower()) or KEYS.get("g")

    def on_key(self, ch=""):
        """敲键 -> 右爪滑到那个键上砸下去; 左爪继续待在鼠标垫上跟鼠标。"""
        self.last_key_t = time.monotonic()
        hit = self.keys_pos(ch) if (PRESS_KEYS and KEYS) else None
        if hit:                                   # 有键位表 -> 右爪滑过去按
            kx, ky = hit
            rx, ry = PAW_BOX["r"][0] + PAW_W // 2, PAW_BOX["r"][1] + PAW_H // 2
            self.tgt["r"] = [min(430.0, max(-430.0, kx - rx)),
                             min(330.0, max(-90.0, ky - ry))]
        self.paw_v["r"] += IMPULSE
        self.up_v["r"] -= 13.0                     # 敲下去: 抬爪量压到 0
        self.body_v += IMPULSE_BODY * 0.7
        self.heat = min(1.0, self.heat + 0.06)

    def on_click(self):
        """鼠标点击 -> 鼠标垫上那只(左爪)按下去。"""
        self.paw_v["l"] += IMPULSE
        self.up_v["l"] -= 11.0
        self.body_v += IMPULSE_BODY * 0.8

    def on_hotkey(self, what):
        if what == "passthrough":
            self.act_passthrough.setChecked(not self.act_passthrough.isChecked())
            self.toggle_passthrough(self.act_passthrough.isChecked())
        elif what == "toggle_show":
            self.act_show.setChecked(not self.act_show.isChecked())
            self.toggle_show(self.act_show.isChecked())

    def toggle_passthrough(self, on):
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        self.show()

    def toggle_show(self, on):
        self.setVisible(on)

    def set_scale(self, sc):
        self.scale = sc
        self._resize()
        self._clamp()
        self.save_cfg()

    # ---------------------------------------------------------------- 每帧
    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now

        if self.demo and random.random() < dt * 7.0:
            self.on_key()

        # 右爪: 跟着鼠标走(屏幕 x/y 映射到桌面上的一小片范围)
        try:
            if not FOLLOW_MOUSE:
                raise StopIteration
            from PySide6.QtGui import QCursor
            mp = QCursor.pos()
            scr = self.screen().availableGeometry()
            fx = (mp.x() - scr.center().x()) / max(1.0, scr.width() / 2.0)
            fy = (mp.y() - scr.center().y()) / max(1.0, scr.height() / 2.0)
            self.tgt["l"] = [MOUSE_DX[0] + (MOUSE_DX[1] - MOUSE_DX[0]) * (fx + 1) / 2.0,
                             MOUSE_DY[0] + (MOUSE_DY[1] - MOUSE_DY[0]) * (fy + 1) / 2.0]
        except Exception:
            pass

        typing = (now - self.last_key_t) < HOVER_KEEP
        for k in ("l", "r"):
            # 落地冲击(驱动压扁)
            acc = -K_HIT * self.paw[k] - C_HIT * self.paw_v[k]
            self.paw_v[k] += acc * dt
            self.paw[k] = min(1.35, max(0.0, self.paw[k] + self.paw_v[k] * dt))
            # 抬爪量: 打字时悬空(1), 停手后落回桌面(0)
            goal = 1.0 if typing else 0.0
            acc = -HOVER_K * (self.up[k] - goal) - HOVER_C * self.up_v[k]
            self.up_v[k] += acc * dt
            self.up[k] = min(1.25, max(0.0, self.up[k] + self.up_v[k] * dt))
            # 平移: 滑向目标(去按键 / 跟鼠标)
            for i in (0, 1):
                d = self.tgt[k][i] - self.off[k][i]
                acc = FOLLOW_K * d - FOLLOW_C * self.off_v[k][i]
                self.off_v[k][i] += acc * dt
                self.off[k][i] += self.off_v[k][i] * dt
        acc = -K_BODY * self.body - C_BODY * self.body_v
        self.body_v += acc * dt
        self.body = min(1.35, max(0.0, self.body + self.body_v * dt))

        self.heat *= math.exp(-dt * 0.55)

        if now >= self.next_blink:
            self.blink_t0 = now
            self.next_blink = now + random.uniform(2.6, 6.5) - 1.6 * self.heat
        self.update()

    def blink_alpha(self, now):
        t = now - self.blink_t0
        if t < 0:
            return 0.0
        if t < BLINK_CLOSE:
            k = t / BLINK_CLOSE
        elif t < BLINK_CLOSE + BLINK_HOLD:
            return 1.0
        elif t < BLINK_CLOSE + BLINK_HOLD + BLINK_OPEN:
            k = 1.0 - (t - BLINK_CLOSE - BLINK_HOLD) / BLINK_OPEN
        else:
            return 0.0
        return k * k * (3 - 2 * k)

    def draw_keys_debug(self, painter):
        """--keydebug: 把所有键位画在底图上, 用来肉眼核对键位表准不准。"""
        s = self.scale
        painter.setPen(QColor(255, 40, 40))
        f = painter.font(); f.setPointSize(9); painter.setFont(f)
        for ch, (kx, ky) in KEYS.items():
            painter.drawLine(int((kx - 8) * s), int(ky * s), int((kx + 8) * s), int(ky * s))
            painter.drawLine(int(kx * s), int((ky - 8) * s), int(kx * s), int((ky + 8) * s))
            painter.drawText(int((kx + 9) * s), int((ky - 9) * s), ch.upper() if ch != " " else "SP")

    def draw_frame(self, painter, w, h, now):
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        s = self.scale

        # 整体: 锚在底边纵向压缩 —— 桌子(在底部)几乎不动, 头肩下沉, 这就是 Bongo Cat 的弹跳
        painter.save()
        painter.translate(w / 2.0, h)
        painter.scale(1.0 + BODY_WIDEN * self.body, 1.0 - BODY_SQUASH * self.body)
        painter.translate(-w / 2.0, -h)
        painter.drawPixmap(0, 0, self.pm_base.scaled(int(SPRITE_W * s), int(SPRITE_H * s),
                                                     Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        for k in ("l", "r"):                       # 爪子: 抬升/落下 + 滑向目标 + 落地压扁
            v = self.paw[k]
            bmp = self.paw_bmp[k]
            bx, by = PAW_BOX[k][0], PAW_BOX[k][1]
            dx, dy = self.off[k]
            painter.save()
            painter.translate((bx + dx) * s, (by + dy - LIFT_PX * self.up[k]) * s)
            painter.scale(1.0 + PAW_WIDEN * v, 1.0 - PAW_SQUASH * v)
            painter.drawPixmap(0, 0, bmp.scaled(int(bmp.width() * s), int(bmp.height() * s),
                                                Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            painter.restore()
        if self.debug_keys:
            self.draw_keys_debug(painter)
        ba = self.blink_alpha(now)
        if ba > 0.01:                              # 闭眼
            painter.setOpacity(ba)
            painter.drawPixmap(int(EYE_BOX[0] * s), int(EYE_BOX[1] * s),
                               self.eyes_bmp.scaled(int(self.eyes_bmp.width() * s),
                                                    int(self.eyes_bmp.height() * s),
                                                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            painter.setOpacity(1.0)
        painter.restore()

    def paintEvent(self, _ev):
        pr = QPainter(self)
        self.draw_frame(pr, self.width(), self.height(), time.monotonic())
        pr.end()

    # ---------------------------------------------------------------- 托盘 / 菜单
    def _make_tray(self):
        self.menu = QMenu(self)
        self.act_show = QAction("显示", self, checkable=True, checked=True)
        self.act_show.triggered.connect(self.toggle_show)
        self.menu.addAction(self.act_show)

        sub = self.menu.addMenu("大小")
        grp = QActionGroup(self)
        for label, sc in (("小 32%", 0.32), ("中 42%", 0.42), ("大 55%", 0.55), ("超大 70%", 0.70)):
            a = QAction(label, self, checkable=True, checked=abs(self.scale - sc) < 1e-6)
            a.triggered.connect(lambda _=False, v=sc: self.set_scale(v))
            grp.addAction(a)
            sub.addAction(a)

        if len(list_skins()) > 1:
            sub = self.menu.addMenu("皮肤")
            grp2 = QActionGroup(self)
            for nm in list_skins():
                try:
                    with open(skin_path(nm, "skin.json"), encoding="utf-8") as fh:
                        label = json.load(fh).get("name", nm)
                except Exception:
                    label = nm
                a = QAction(label, self, checkable=True, checked=(nm == self.skin))
                a.triggered.connect(lambda _=False, v=nm: self.switch_skin(v))
                grp2.addAction(a)
                sub.addAction(a)

        self.act_top = QAction("始终置顶", self, checkable=True,
                               checked=self.cfg.get("on_top", True))
        self.act_top.triggered.connect(self.toggle_top)
        self.menu.addAction(self.act_top)

        self.act_passthrough = QAction("鼠标穿透 (Ctrl+Alt+P)", self, checkable=True)
        self.act_passthrough.triggered.connect(self.toggle_passthrough)
        self.menu.addAction(self.act_passthrough)

        self.menu.addSeparator()
        a = QAction("关于 Moon 桌宠", self); a.triggered.connect(self.show_about)
        self.menu.addAction(a)
        a = QAction("回到右下角", self); a.triggered.connect(self._reset_pos)
        self.menu.addAction(a)
        a = QAction("退出", self); a.triggered.connect(self.quit)
        self.menu.addAction(a)

        self.tray = QSystemTrayIcon(self.tray_icon, self)
        tip = "Moon 桌宠 v%s — 打字时她跟着拍桌子" % VERSION
        if not self.input_ok:
            tip += "\n(全局键鼠监听未启用: %s)" % (self.bridge.error or "")
        self.tray.setToolTip(tip)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(
            lambda r: self.toggle_show(not self.isVisible())
            if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def show_about(self):
        QMessageBox.information(
            self, "关于 Moon 桌宠",
            "Moon 桌宠  v%s  (Bongo Cat 版)\n\n"
            "你打字时，她会左右爪交替拍桌子，整个人跟着往下一沉。\n\n"
            "拖动：左键        菜单：右键        托盘：显示/隐藏\n"
            "Ctrl+Alt+P  鼠标穿透\n"
            "Ctrl+Alt+H  显示 / 隐藏\n\n"
            "素材来自一张 OC 插画，由 tools/bongo_cut.py 自动切分。" % VERSION)

    def toggle_top(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()
        self.cfg["on_top"] = bool(on)
        self.save_cfg()

    def _reset_pos(self):
        self.cfg.pop("x", None); self.cfg.pop("y", None)
        self._place()

    def quit(self):
        self.cfg["x"], self.cfg["y"] = self.x(), self.y()
        self.save_cfg()
        QApplication.quit()

    # ---------------------------------------------------------------- 配置
    def _load_cfg(self):
        try:
            with open(CONFIG, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_cfg(self):
        self.cfg.update(x=self.x(), y=self.y(), scale=self.scale,
                        on_top=self.act_top.isChecked())
        try:
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ----------------------------------------------------------------------------- 自检
def selftest(out_path):
    app = QApplication.instance() or QApplication(sys.argv)
    pet = Pet(skin=_arg("--skin"))
    states = [("idle", 0.0, 0.0, (0, 0), (0, 0)),
              ("hover", 1.0, 1.0, (0, 0), (0, 0)),
              ("press G", 1.0, 0.0, (0, 0), None),
              ("press P", 1.0, 0.0, (0, 0), None),
              ("press 5", 1.0, 0.0, (0, 0), None)]
    # 后三个状态用真实键位算出右爪位置(皮肤没有键位表时就不平移, 只砸)
    for i, ch in enumerate(("g", "p", "5")):
        p_ = pet.keys_pos(ch)
        if p_ is None:
            states[2 + i] = (states[2 + i][0], states[2 + i][1], 0.0, (0, 0), (0, 0))
            continue
        states[2 + i] = (states[2 + i][0], states[2 + i][1], 0.0, (0, 0),
                         (p_[0] - (PAW_BOX["r"][0] + PAW_W // 2),
                          p_[1] - (PAW_BOX["r"][1] + PAW_H // 2)))
    w, h = pet.width(), pet.height()
    canvas = QPixmap(int(w * len(states) + 8 * (len(states) - 1)), h)
    canvas.fill(QColor(36, 38, 48))
    pr = QPainter(canvas)
    for i, (_n, ul, ur, ol, orr) in enumerate(states):
        pet.up["l"], pet.up["r"] = ul, ur
        pet.off["l"] = list(ol)
        pet.off["r"] = list(orr)
        pet.paw["l"] = pet.paw["r"] = pet.body = 0.0
        pet.blink_t0 = time.monotonic() if i == len(states) - 1 else -99.0
        pr.save()
        pr.translate(i * (w + 8), 0)
        pet.draw_frame(pr, w, h, time.monotonic())
        pr.restore()
    pr.end()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path)
    print("selftest ->", out_path, canvas.width(), "x", canvas.height())


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and len(sys.argv) > sys.argv.index(name) + 1 else default


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "build/selftest_bongo.png")
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet(skin=_arg("--skin"))
    pet.demo = "--demo" in sys.argv
    pet.debug_keys = "--keydebug" in sys.argv
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
