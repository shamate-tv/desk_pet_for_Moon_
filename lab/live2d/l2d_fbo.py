import os, sys
os.environ.setdefault("QT_OPENGL", "desktop")
from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
from PySide6.QtWidgets import QApplication
from OpenGL import GL
import numpy as np
app = QApplication(sys.argv)
fmt = QSurfaceFormat(); fmt.setVersion(2,1); fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
QSurfaceFormat.setDefaultFormat(fmt)
surf = QOffscreenSurface(); surf.setFormat(fmt); surf.create()
ctx = QOpenGLContext(); ctx.setFormat(fmt); ctx.create(); ctx.makeCurrent(surf)
import live2d
live2d.init(); live2d.glInit()

W,H = 600,900
fbo = GL.glGenFramebuffers(1); tex = GL.glGenTextures(1)
GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA8,W,H,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,None)
GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
print("FBO status:", GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) == GL.GL_FRAMEBUFFER_COMPLETE)
GL.glViewport(0,0,W,H)
GL.glClearColor(1,0,0,1); GL.glClear(GL.GL_COLOR_BUFFER_BIT); GL.glFinish()
b = np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,4)
print("FBO 读回测试:", b[H-1,0], "(期望 [255 0 0 255])")

m = live2d.Model(); m.LoadModelJson(os.path.abspath("build/live2d_sample/Haru/Haru.model3.json"))
m.Resize(W,H); m.SetAutoBreath(True); m.SetAutoBlink(True)
try: m.StartMotion("Idle", 0, 3)
except Exception as e: print("StartMotion:", e)
for i in range(40): m.Update(1/60.0)
live2d.clearBuffer(0,0,0,0); m.Draw(); GL.glFinish()
b2 = np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,4)
n = (b2[...,3]>8).sum()
print("模型非透明像素:", n)
if n:
    ys,xs = np.nonzero(b2[...,3]>8)
    print("  内容 x %d-%d  y(自下) %d-%d" % (xs.min(),xs.max(),ys.min(),ys.max()))
    from PIL import Image
    img = b2[::-1]
    bg = Image.new("RGBA",(W,H),(245,245,248,255)); bg.alpha_composite(Image.fromarray(img,"RGBA"))
    bg.convert("RGB").save("build/live2d_spike.png"); print("-> build/live2d_spike.png")
