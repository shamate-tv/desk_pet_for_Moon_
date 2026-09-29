# -*- coding: utf-8 -*-
"""Moon 桌宠 —— Bongo Cat 式打字反馈。

  打字 -> 手绕腕关节按下(并带动身体轻微下压), 空闲 -> 随机眨眼, 鼠标点击 -> 一次轻微点头。

素材: assets/base.png(底图) / hand.png(手) / lid.png(眼皮)   (由 tools/step*.py 生成)
运行: python pet/main.py            正常启动
      python pet/main.py --demo     演示模式(自动模拟打字, 不用真的敲键盘)
      python pet/main.py --selftest build/selftest.png   离屏渲染各状态, 用于验收

热键: Ctrl+Alt+P 鼠标穿透开关    Ctrl+Alt+H 显示/隐藏
"""
import os
import sys
import json
import math
import random
import time

from PySide6.QtCore import Qt, QTimer, QPoint, QObject, Signal, QRectF
from PySide6.QtGui import (QPixmap, QPainter, QTransform, QImage, QAction, QActionGroup,
                           QIcon, QCursor, QColor)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon

# ----------------------------------------------------------------------------- 常量
# 打包成 exe 后: 素材在 exe 内部(sys._MEIPASS), 配置写在 exe 旁边(可写)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR
ASSETS = os.path.join(RES_DIR, "assets")
CONFIG = os.path.join(BASE_DIR, "config.json")

SPRITE_W, SPRITE_H = 768, 1123
HAND_BOX = (170, 900, 512, 1105)          # 手层在画布中的位置
PIVOT = (470.0, 1030.0)                   # 腕关节 = 旋转轴(全图坐标)
LID_BOX = (325, 335, 415, 396)

ANG_MIN, ANG_STEP, ANG_N = -1.0, 0.1, 51  # 手部旋转预渲染: -1.0° ~ +4.0°
PRESS_ANGLE = 2.0                         # 按键时手的旋转角(度); 越大越夸张, 但露出补洞区的带宽也越大
ATTACK, RELEASE = 26.0, 13.0              # 按下/回弹 的收敛速度(越大越快)
KEY_PULSE = 0.085                         # 极短促的按键也要保证手有可见动作(秒)
BODY_SQUASH = 0.0026                      # 按键时整身纵向压缩比例(打击感)
TAP_SQUASH = 0.0022                       # 鼠标点击的点头幅度
BLINK_CLOSE, BLINK_HOLD, BLINK_OPEN = 0.05, 0.04, 0.075
FPS = 60


# ----------------------------------------------------------------------------- 输入
class InputBridge(QObject):
    """把 pynput 的全局键鼠事件转到 Qt 主线程(信号跨线程自动排队)。"""
    key_press = Signal()
    clicked = Signal()
    hotkey = Signal(str)

    def __init__(self):
        super().__init__()
        self.mods = set()
        self._kb = None
        self._ms = None
        self.error = None

    def start(self):
        try:
            from pynput import keyboard, mouse
        except Exception as exc:                                   # pragma: no cover
            self.error = "pynput 不可用: %s" % exc
            return False
        try:
            def on_press(key):
                name = getattr(key, "name", None) or str(key).lstrip("Key.")
                if "ctrl" in name:
                    self.mods.add("ctrl")
                elif "alt" in name:
                    self.mods.add("alt")
                if self.mods >= {"ctrl", "alt"}:
                    if name == "p":
                        self.hotkey.emit("passthrough")
                    elif name == "h":
                        self.hotkey.emit("toggle_show")
                self.key_press.emit()          # 只看"有没有按", 不记录按了什么

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
        except Exception as exc:                                   # pragma: no cover
            self.error = "全局钩子启动失败: %s" % exc
            return False


# ----------------------------------------------------------------------------- 桌宠
class Pet(QWidget):
    def __init__(self, scale=0.55):
        super().__init__()
        self.cfg = self._load_cfg()
        self.scale = float(self.cfg.get("scale", scale))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            (Qt.WindowStaysOnTopHint if self.cfg.get("on_top", True) else Qt.WindowNoState))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Moon Pet")

        self._load_assets()
        self._resize()

        # 状态
        self.keys = 0
        self.press_until = 0.0
        self.angle = 0.0
        self.impact = 0.0
        self.heat = 0.0
        self.blink_t0 = -9.0
        self.next_blink = time.monotonic() + random.uniform(2.5, 6.0)
        self.demo = False
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
        p = lambda n: os.path.join(ASSETS, n)
        # 底图必须用 base.png(手背后已补洞), 不能用 sprite.png(原图, 手还在里面):
        # 手绕腕旋转时会让开一部分原来的位置, 用 sprite 打底就会露出原手的重影。
        self.pm_base = QPixmap(p("base.png"))
        hand = QPixmap(p("hand.png"))
        self.pm_lid = QPixmap(p("lid.png"))
        if self.pm_base.isNull() or hand.isNull() or self.pm_lid.isNull():
            raise SystemExit("assets 缺失, 先运行 tools/step1_matte.py / step2_hand.py / step3_eye.py")
        self.hand_bmp = hand.copy(*HAND_BOX)
        self.lid_bmp = self.pm_lid.copy(*LID_BOX)
        self.hand_cache = self._build_hand_cache()
        self.tray_icon = self._make_icon()

    def _build_hand_cache(self):
        """把手的旋转预渲染成若干张(避免每帧重采样整幅图)。"""
        px, py = PIVOT[0] - HAND_BOX[0], PIVOT[1] - HAND_BOX[1]
        cache = []
        dpr = self.hand_bmp.devicePixelRatio()
        for i in range(ANG_N):
            ang = ANG_MIN + i * ANG_STEP
            out = QPixmap(self.hand_bmp.size())
            out.setDevicePixelRatio(dpr)
            out.fill(Qt.transparent)
            pr = QPainter(out)
            pr.setRenderHint(QPainter.SmoothPixmapTransform, True)
            pr.translate(px, py)
            pr.rotate(ang)
            pr.translate(-px, -py)
            pr.drawPixmap(0, 0, self.hand_bmp)
            pr.end()
            cache.append(out)
        return cache

    def _make_icon(self):
        head = self.pm_base.copy(150, 30, 300, 300)          # 头肩
        head = head.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QPixmap(64, 64)
        icon.fill(Qt.transparent)
        pr = QPainter(icon)
        pr.setRenderHint(QPainter.Antialiasing)
        pr.setBrush(QColor(30, 30, 34))
        pr.setPen(Qt.NoPen)
        pr.drawEllipse(0, 0, 64, 64)
        pr.drawPixmap(0, 0, head)
        pr.end()
        return QIcon(icon)

    # ---------------------------------------------------------------- 窗口
    def _resize(self):
        self.setFixedSize(int(SPRITE_W * self.scale), int((SPRITE_H + 6) * self.scale))

    def _place(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x = self.cfg.get("x"); y = self.cfg.get("y")
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

    def mouseReleaseEvent(self, ev):
        self.drag_from = None

    def contextMenuEvent(self, ev):
        self.menu.exec(ev.globalPos())

    def on_key(self):
        self.keys += 1
        self.press_until = time.monotonic() + KEY_PULSE
        self.heat = min(1.0, self.heat + 0.06)

    def on_click(self):
        self.impact = 1.0

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
        dt = min(0.1, now - self.last)
        self.last = now

        if self.demo:
            if random.random() < dt * 6.0:
                self.on_key()

        # 手: 按下快, 回弹慢
        pressed = self.keys > 0 or now < self.press_until
        target = (PRESS_ANGLE + 0.8 * self.heat) if pressed else 0.0
        rate = ATTACK if target > self.angle else RELEASE
        self.angle += (target - self.angle) * min(1.0, rate * dt)
        self.keys = 0
        self.heat *= math.exp(-dt * 0.55)

        self.impact *= math.exp(-dt * 22.0)

        # 眨眼
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
        return k * k * (3 - 2 * k)                      # smoothstep

    def draw_frame(self, painter, w, h, now):
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)

        squash = 1.0 - BODY_SQUASH * (self.angle / max(PRESS_ANGLE, 1e-6)) - TAP_SQUASH * self.impact
        painter.save()
        painter.translate(w / 2.0, h)                    # 以底边中心为锚点做整体压缩
        painter.scale(1.0, squash)
        painter.translate(-w / 2.0, -h)
        s = self.scale
        painter.drawPixmap(0, 0, self.pm_base.scaled(int(SPRITE_W * s), int(SPRITE_H * s),
                                                     Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        idx = int(round((self.angle - ANG_MIN) / ANG_STEP))
        idx = max(0, min(ANG_N - 1, idx))
        hb = self.hand_cache[idx]
        painter.drawPixmap(int(HAND_BOX[0] * s), int(HAND_BOX[1] * s),
                           hb.scaled(int(hb.width() * s), int(hb.height() * s),
                                     Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        ba = self.blink_alpha(now)
        if ba > 0.01:
            painter.setOpacity(ba)
            painter.drawPixmap(int(LID_BOX[0] * s), int(LID_BOX[1] * s),
                               self.lid_bmp.scaled(max(1, int(self.lid_bmp.width() * s)),
                                                   max(1, int(self.lid_bmp.height() * s)),
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
        for label, sc in (("小 45%", 0.45), ("中 55%", 0.55), ("大 70%", 0.70), ("超大 85%", 0.85)):
            a = QAction(label, self, checkable=True, checked=abs(self.scale - sc) < 1e-6)
            a.triggered.connect(lambda _=False, s=sc: self.set_scale(s))
            grp.addAction(a)
            sub.addAction(a)

        self.act_top = QAction("始终置顶", self, checkable=True, checked=self.cfg.get("on_top", True))
        self.act_top.triggered.connect(self.toggle_top)
        self.menu.addAction(self.act_top)

        self.act_passthrough = QAction("鼠标穿透 (Ctrl+Alt+P)", self, checkable=True)
        self.act_passthrough.triggered.connect(self.toggle_passthrough)
        self.menu.addAction(self.act_passthrough)

        self.menu.addSeparator()
        a = QAction("回到右下角", self); a.triggered.connect(self._reset_pos)
        self.menu.addAction(a)
        a = QAction("退出", self); a.triggered.connect(self.quit)
        self.menu.addAction(a)

        self.tray = QSystemTrayIcon(self.tray_icon, self)
        tip = "Moon 桌宠 — 打字时会敲键盘"
        if not self.input_ok:
            tip += "\n(全局键鼠监听未启用: %s)" % (self.bridge.error or "")
        self.tray.setToolTip(tip)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(
            lambda r: self.toggle_show(not self.isVisible()) if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

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
        self.cfg.update(x=self.x(), y=self.y(), scale=self.scale, on_top=self.act_top.isChecked())
        try:
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ----------------------------------------------------------------------------- 自检
def selftest(out_path):
    """离屏渲染若干状态拼成一张图, 用来验收动作与抠像边缘。"""
    app = QApplication.instance() or QApplication(sys.argv)
    pet = Pet()
    states = [("idle 0°", 0.0, 0.0), ("press 1.0°", 1.0, 0.0), ("press 2.0°", 2.0, 0.0),
              ("press 3.0°", 3.0, 0.0), ("blink", 0.0, 1.0)]
    w, h = pet.width(), pet.height()
    canvas = QPixmap(int(w * len(states) + 8 * (len(states) - 1)), h)
    canvas.fill(QColor(38, 40, 48))
    pr = QPainter(canvas)
    old = (pet.angle, pet.impact, pet.blink_t0, pet.scale)
    for i, (_n, ang, blink) in enumerate(states):
        pet.angle, pet.impact = ang, 0.0
        pet.blink_t0 = time.monotonic() if blink else -99.0
        pr.save()
        pr.translate(i * (w + 8), 0)
        pet.draw_frame(pr, w, h, time.monotonic())
        pr.restore()
    pr.end()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path)
    pet.angle, pet.impact, pet.blink_t0, pet.scale = old
    print("selftest ->", out_path, canvas.width(), "x", canvas.height())


def main():
    demo = "--demo" in sys.argv
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "build/selftest.png")
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet()
    pet.demo = demo
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
