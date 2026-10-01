import os, sys, time
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

def bench(W,H,readback=True,n=120):
    fbo = GL.glGenFramebuffers(1); tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA8,W,H,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,None)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
    GL.glViewport(0,0,W,H)
    m = live2d.Model(); m.LoadModelJson(os.path.abspath("build/live2d_sample/Haru/Haru.model3.json"))
    m.Resize(W,H); m.SetAutoBreath(True); m.SetAutoBlink(True)
    for _ in range(30): m.Update(1/60.0)
    ts=[]
    for _ in range(n):
        t0=time.perf_counter()
        m.Update(1/60.0)
        live2d.clearBuffer(0,0,0,0)
        m.Draw()
        if readback:
            GL.glFinish()
            GL.glReadPixels(0,0,W,H,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE)
        ts.append((time.perf_counter()-t0)*1000)
    GL.glDeleteFramebuffers(1,[fbo]); GL.glDeleteTextures(1,[tex])
    return np.mean(ts), np.percentile(ts,95)

for (W,H) in ((600,900),(420,630)):
    a,p = bench(W,H,True)
    b,q = bench(W,H,False)
    print("%3dx%-4d  含读回: %.2f ms (p95 %.2f, 约 %.0f fps)   不含读回: %.2f ms" % (W,H,a,p,1000/a,b))
