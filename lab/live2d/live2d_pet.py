# -*- coding: utf-8 -*-
"""Live2D 桌宠 · 集成演示（假模型用的官方示例 Haru）

目的：证明 Live2D 能无缝接进我们这套壳 —— 透明窗口 / 置顶 / 拖拽 / 托盘 /
      全局键鼠钩子 / config.json 全都不动，只把"贴图层"换成"贴 Live2D 帧"。

实现要点（已验证）：
  * Qt 离屏 GL 上下文 + 自建 FBO —— 离屏表面的默认帧缓冲读不到，必须用 FBO
  * live2d.Model 渲染完 → glReadPixels → numpy → QImage → QPainter 贴到窗口上
  * 打字 -> StartMotion("TapBody")（对应 Bongo 的"拍一下"）
  * 鼠标 -> ParamAngleX/Y/Z + ParamEyeBallX/Y + ParamBodyAngleX（这是我们现在做不了的"跟随鼠标"）

运行：python pet/live2d_pet.py
"""
import os
import sys
import json
import random
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QImage, QPainter, QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon

# ----------------------------------------------------------------------------- 路径
VERSION = "2.0.1-l2d-demo"
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR
CONFIG = os.path.join(BASE_DIR, "config_l2d.json")

MODEL_JSON = os.path.join(RES_DIR, "models", "Haru", "Haru.model3.json")
CANVAS_W, CANVAS_H = 600, 900          # Live2D 渲染分辨率
DEFAULT_SCALE = 0.5
FPS = 60
MOTION_COOLDOWN = 0.35                 # 敲键触发动作的最小间隔(秒)
ROAM_MS = 1000.0                       # 鼠标跟进速度

# 参数名（不同模型可能没有，运行时用 GetParamIds 过滤）
P_ANGLE_X, P_ANGLE_Y, P_ANGLE_Z = "ParamAngleX", "ParamAngleY", "ParamAngleZ"
P_EYE_X, P_EYE_Y = "ParamEyeBallX", "ParamEyeBallY"
P_BODY_X, P_BREATH = "ParamBodyAngleX", "ParamBreath"


# ----------------------------------------------------------------------------- Live2D
class Live2DView:
    """离屏 GL + FBO 渲染 Live2D，每帧给出一张 QImage。"""

    def __init__(self, model_json, w=CANVAS_W, h=CANVAS_H):
        from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
        from OpenGL import GL
        self.GL = GL
        self.w, self.h = w, h

        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
        fmt.setDepthBufferSize(24)
        self.surf = QOffscreenSurface()
        self.surf.setFormat(fmt)
        self.surf.create()
        self.ctx = QOpenGLContext()
        self.ctx.setFormat(fmt)
        self.ctx.create()
        if not self.ctx.makeCurrent(self.surf):
            raise RuntimeError("无法建立 OpenGL 上下文")

        import live2d
        self.live2d = live2d
        live2d.init()
        live2d.glInit()

        self.model = live2d.Model()
        self.model.LoadModelJson(model_json)
        self.model.Resize(w, h)
        self.model.SetAutoBreath(True)
        self.model.SetAutoBlink(True)
        try:
            self.model.SetScale(1.05)
        except Exception:
            pass

        self.params = set(self.model.GetParamIds())
        self.motions = self._motion_groups(model_json)
        self._make_fbo()

    @staticmethod
    def _motion_groups(model_json):
        try:
            with open(model_json, encoding="utf-8") as fh:
                data = json.load(fh)
            groups = {}
            for g in data.get("FileReferences", {}).get("Motions", []):
                groups[g["Name"]] = len(g["File"])
            return groups
        except Exception:
            return {}

    def _make_fbo(self):
        GL = self.GL
        self.fbo = GL.glGenFramebuffers(1)
        self.tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.tex)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, self.w, self.h, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                  GL.GL_TEXTURE_2D, self.tex, 0)
        if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("FBO 创建失败")
        GL.glViewport(0, 0, self.w, self.h)

    def set_param(self, pid, value, weight=1.0):
        if pid in self.params:
            self.model.SetParamById(pid, float(value), float(weight))

    def play_motion(self, group=None):
        if not self.motions:
            return
        group = group or ("TapBody" if "TapBody" in self.motions else next(iter(self.motions)))
        self.model.StartMotion(group, random.randrange(self.motions[group]), 2)

    def render(self, dt):
        GL = self.GL
        self.ctx.makeCurrent(self.surf)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glViewport(0, 0, self.w, self.h)
        self.model.Update(dt)
        self.live2d.clearBuffer(0, 0, 0, 0)
        self.model.Draw()
        GL.glFinish()
        buf = GL.glReadPixels(0, 0, self.w, self.h, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        arr = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 4)[::-1].copy()
        img = QImage(arr.data, self.w, self.h, self.w * 4, QImage.Format_RGBA8888).copy()
        return img


# ----------------------------------------------------------------------------- 输入
class InputBridge(QObject):
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
                ch = getattr(key, "char", None)
                if ch:
                    if len(ch) == 1 and ord(ch) < 32:
                        ch = chr(ord(ch) + 96)
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
                self.key_press.emit(nm)

            def on_release(key):
                nm = (getattr(key, "name", None) or "").lower()
                if "ctrl" in nm:
                    self.mods.discard("ctrl")
                elif "alt" in nm:
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
class Live2DPet(QWidget):
    def __init__(self, scale=DEFAULT_SCALE):
        super().__init__()
        self.cfg = self._load_cfg()
        self.scale = float(self.cfg.get("scale", scale))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Moon 桌宠 v%s (Live2D)" % VERSION)

        self.view = Live2DView(MODEL_JSON)
        self._resize()
        self._place()

        self.keys = 0
        self.last_motion = 0.0
        self.aim = [0.0, 0.0]          # 平滑后的鼠标方向
        self.drag_from = None
        self.cursor_on = self.cfg.get("cursor", True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.last = time.monotonic()
        self.timer.start(int(1000 / FPS))

        self.bridge = InputBridge()
        self.bridge.key_press.connect(self.on_key)
        self.bridge.clicked.connect(self.on_click)
        self.bridge.hotkey.connect(self.on_hotkey)
        self.input_ok = self.bridge.start()
        self._make_tray()

    # ---------------------------------------------------------------- 窗口
    def _resize(self):
        self.setFixedSize(int(self.view.w * self.scale), int(self.view.h * self.scale))

    def _place(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            x = scr.right() - self.width() - 30
            y = scr.bottom() - self.height() + 6
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

    def on_key(self, _ch=""):
        self.keys += 1
        now = time.monotonic()
        if now - self.last_motion > MOTION_COOLDOWN:
            self.view.play_motion()
            self.last_motion = now

    def on_click(self):
        now = time.monotonic()
        if now - self.last_motion > MOTION_COOLDOWN:
            self.view.play_motion()
            self.last_motion = now

    def on_hotkey(self, what):
        if what == "passthrough":
            self.act_passthrough.setChecked(not self.act_passthrough.isChecked())
            self.toggle_passthrough(self.act_passthrough.isChecked())
        elif what == "toggle_show":
            self.act_show.setChecked(not self.act_show.isChecked())
            self.setVisible(self.act_show.isChecked())

    def toggle_passthrough(self, on):
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        self.show()

    def toggle_cursor(self, on):
        self.cursor_on = bool(on)
        self.cfg["cursor"] = self.cursor_on
        self.save_cfg()

    def set_scale(self, sc):
        self.scale = sc
        self._resize()
        self.save_cfg()

    # ---------------------------------------------------------------- 每帧
    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now

        if self.cursor_on:                       # 鼠标 -> 头/眼跟随（Live2D 的招牌能力）
            from PySide6.QtGui import QCursor
            mp = QCursor.pos()
            g = self.frameGeometry()
            dx = (mp.x() - g.center().x()) / max(1.0, g.width() * 1.2)
            dy = (mp.y() - g.center().y()) / max(1.0, g.height() * 1.2)
            k = min(1.0, dt * 6.0)
            self.aim[0] += (max(-1.0, min(1.0, dx)) - self.aim[0]) * k
            self.aim[1] += (max(-1.0, min(1.0, dy)) - self.aim[1]) * k
            v = self.view
            v.set_param(P_ANGLE_X, 30 * self.aim[0])
            v.set_param(P_ANGLE_Y, -30 * self.aim[1])
            v.set_param(P_ANGLE_Z, 8 * self.aim[0])
            v.set_param(P_EYE_X, self.aim[0])
            v.set_param(P_EYE_Y, -self.aim[1])
            v.set_param(P_BODY_X, 10 * self.aim[0])
        self.update()

    def paintEvent(self, _ev):
        frame = self.view.render(1.0 / FPS)
        pr = QPainter(self)
        pr.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pr.drawImage(self.rect(), frame)
        pr.end()

    # ---------------------------------------------------------------- 托盘
    def _make_tray(self):
        self.menu = QMenu(self)
        self.act_show = QAction("显示", self, checkable=True, checked=True)
        self.act_show.triggered.connect(self.setVisible)
        self.menu.addAction(self.act_show)

        sub = self.menu.addMenu("大小")
        for label, sc in (("小 35%", 0.35), ("中 50%", 0.5), ("大 65%", 0.65), ("超大 85%", 0.85)):
            a = QAction(label, self, checkable=True, checked=abs(self.scale - sc) < 1e-6)
            a.triggered.connect(lambda _=False, v=sc: self.set_scale(v))
            sub.addAction(a)

        self.act_cursor = QAction("跟随鼠标（头/眼）", self, checkable=True, checked=self.cursor_on)
        self.act_cursor.triggered.connect(self.toggle_cursor)
        self.menu.addAction(self.act_cursor)

        self.act_passthrough = QAction("鼠标穿透 (Ctrl+Alt+P)", self, checkable=True)
        self.act_passthrough.triggered.connect(self.toggle_passthrough)
        self.menu.addAction(self.act_passthrough)

        self.menu.addSeparator()
        a = QAction("退出", self); a.triggered.connect(self.quit)
        self.menu.addAction(a)

        icon = QPixmap(64, 64)
        icon.fill(QColor(32, 30, 40))
        self.tray = QSystemTrayIcon(QIcon(icon), self)
        tip = "Moon 桌宠 v%s (Live2D 演示)" % VERSION
        if not self.input_ok:
            tip += "\n(全局键鼠监听未启用: %s)" % (self.bridge.error or "")
        self.tray.setToolTip(tip)
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def quit(self):
        self.cfg.update(x=self.x(), y=self.y(), scale=self.scale, cursor=self.cursor_on)
        self.save_cfg()
        QApplication.quit()

    def _load_cfg(self):
        try:
            with open(CONFIG, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_cfg(self):
        try:
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass


def main():
    if "--shot" in sys.argv:                     # 离屏出一张图, 便于无窗口验收
        out = sys.argv[sys.argv.index("--shot") + 1] if len(sys.argv) > sys.argv.index("--shot") + 1 \
            else "build/live2d_demo_shot.png"
        app = QApplication(sys.argv)
        view = Live2DView(MODEL_JSON)
        view.play_motion()
        for _ in range(60):
            view.model.Update(1 / 60.0)
        img = view.render(1 / 60.0)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        img.save(out)
        print("shot ->", out, img.width(), "x", img.height())
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Live2DPet()
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
