# -*- coding: utf-8 -*-
"""把 Moon 的分层素材直接编译成 Live2D 模型(.moc3) —— 不用 Cubism Editor。

路线来源: fifteen42/live2d-from-art 的 MIT 许可实验性序列化器(见同目录 py-moc3/)。
它不是官方编译器; 产出物能被官方 Cubism Core 加载(本脚本最后会用 live2d-py 实测)。

M1 目标: 静态模型 —— 3 个 drawable(背景板 / 左手 / 右手) + 2 个参数(左右爪, 暂为单关键形),
        加载后画面应与原画一致。

用法:
    python tools/make_live2d.py                 # 生成到 build/moc3/Moon/
    python tools/make_live2d.py --verify        # 生成后再用官方 Core 加载渲染验证
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MOC3_SRC = ROOT / "lab" / "live2d" / "moc3" / "py-moc3" / "src"
sys.path.insert(0, str(MOC3_SRC))

from moc3 import Moc3                                     # noqa: E402
from moc3._core import SECTION_LAYOUT, ElemType, SectionEntry   # noqa: E402

# 上游这张表有两组计数索引对调了, 案例里就是这么修的 —— 不修的话 Core 直接拒载。
SECTION_LAYOUT[41], SECTION_LAYOUT[44] = SECTION_LAYOUT[44], SECTION_LAYOUT[41]
SECTION_LAYOUT[82], SECTION_LAYOUT[83] = SECTION_LAYOUT[83], SECTION_LAYOUT[82]

# ---- 素材: 直接用皮肤目录里的三层(全画布同尺寸, 已经对齐好了) ----
SKIN = ROOT / "skins" / "moon"
LAYERS = [("bg", "bg.png"), ("PawL", "paw_l.png"), ("PawR", "paw_r.png")]
OUT_DIR = ROOT / "build" / "moc3" / "Moon"

CANVAS_W, CANVAS_H = 1459, 1078
PPU = 1000.0                     # 每单位多少像素(Cubism 常用 1000)
ORIGIN_X, ORIGIN_Y = CANVAS_W / 2.0, CANVAS_H / 2.0
ATLAS = 4096
COLS, ROWS = 7, 11               # 每片的网格点数(演示级; 形状简单够用)
NV = COLS * ROWS                 # 每片顶点数
NF = NV * 2                      # 每片 float 数
STRIDE = ((NF + 15) // 16) * 16  # 关键形里每个位置块按 16 float 对齐
NI = (COLS - 1) * (ROWS - 1) * 6 # 每片三角形索引数

LIFT_PX = 40.0                   # 抬爪高度(原图像素): 参数=0(默认) 时抬这么高, =1 时拍在桌面上

# 参数名/范围/默认值全部对齐 BongoCat 的约定(取自它的参考模型 demomodel2.moc3):
#   CatParamLeftHandDown / CatParamRightHandDown  [0,1] default 0  —— 1 = 手按下去
# 其余参数是为了兼容 BongoCat 可能去设置的其它参数(静态, 设了也不会崩)。
#   名字, 最小值, 最大值, 默认值, 关键形取值
PARAMS = [
    ("ParamAngleX", -30, 30, 0, [0.0]),
    ("ParamAngleY", -30, 30, 0, [0.0]),
    ("CatParamRightHandDown", 0, 1, 0, [0.0, 1.0]),
    ("CatParamLeftHandDown", 0, 1, 0, [0.0, 1.0]),
    ("ParamAngleZ", -30, 30, 0, [0.0]),
    ("ParamEyeLOpen", 0, 1, 1, [1.0]),
    ("ParamEyeROpen", 0, 1, 1, [1.0]),
    ("ParamEyeBallX", -1, 1, 0, [0.0]),
    ("ParamEyeBallY", -1, 1, 0, [0.0]),
    ("ParamBrowLY", -1, 1, 0, [0.0]),
    ("ParamBrowRY", -1, 1, 0, [0.0]),
    ("ParamMouthForm", -1, 1, 0, [0.0]),
    ("ParamMouthOpenY", 0, 1, 0, [0.0]),
    ("ParamCheek", 0, 1, 0, [0.0]),
    ("ParamBodyAngleX", -10, 10, 0, [0.0]),
    ("ParamBodyAngleY", -10, 10, 0, [0.0]),
    ("ParamBodyAngleZ", -10, 10, 0, [0.0]),
    ("ParamBreath", 0, 1, 0, [0.0]),
    ("ParamMouseX", -1, 1, 0, [0.0]),
    ("ParamMouseY", -1, 1, 0, [0.0]),
    ("ParamMouseLeftDown", 0, 1, 0, [0.0]),
    ("ParamMouseRightDown", 0, 1, 0, [0.0]),
    ("Param", 0, 1, 0, [0.0, 1.0]),          # 官方模型里它就是"左手"
    ("Param2", 0, 1, 0, [0.0, 1.0]),         # 它就是"右手"
    ("Param3", 0, 30, 0, [0.0]),
    ("Param4", 0, 1, 0, [0.0]),
    ("Param5", 0, 1, 0, [0.0]),
    ("ParamHairFront", -1, 1, 0, [0.0]),
    ("ParamHairSide", -1, 1, 0, [0.0]),
    ("ParamHairBack", -1, 1, 0, [0.0]),
]


def build():
    n = len(LAYERS)
    p = len(PARAMS)
    # 每片绑到哪根参数轴: bg 静态(空轴), 两只爪子各自一根轴
    # 手部 band 用双轴: [猫手参数, 鼠标键参数] —— BongoCat 的 standard 模式推的是
    # ParamMouseLeftDown/RightDown, keyboard 模式推的是 CatParamLeft/RightHandDown,
    # 两轴各 2 个取值 => 每只手 4 个关键形; 只有 (0,0) 是"抬起", 其余都是"拍下去"。
    _idx = {x[0]: i for i, x in enumerate(PARAMS)}
    BANDS = [[], [_idx["Param"]], [_idx["Param2"]]]   # 官方模型: Param=左手, Param2=右手
    DRAWABLE_BANDS = [0, 1, 2]                   # bg / 左手片 / 右手片
    KF_PER = []
    for axes in [BANDS[b] for b in DRAWABLE_BANDS]:
        c = 1
        for ax in axes:
            c *= len(PARAMS[ax][4])
        KF_PER.append(c)
    N_KF = sum(KF_PER)
    m = Moc3()
    m.canvas.pixels_per_unit = PPU
    m.canvas.origin_x = ORIGIN_X
    m.canvas.origin_y = ORIGIN_Y
    m.canvas.canvas_width = CANVAS_W
    m.canvas.canvas_height = CANVAS_H

    # ---- 各段计数 ----
    m.counts[4] = n                  # drawable 数
    m.counts[9] = N_KF               # 关键形总数
    m.counts[10] = STRIDE * N_KF     # 关键形位置 float 总数
    m.counts[15] = NF * n            # 顶点 float 总数
    m.counts[16] = NI * n            # 索引总数
    m.counts[18] = 1                 # 绘制顺序组
    m.counts[19] = n                 # 组内对象数
    m.counts[17] = 0                 # 不用遮罩
    m.counts[5] = p                  # 参数数
    m.counts[13] = p
    for e in SECTION_LAYOUT:         # 所有运行时段先铺零
        if e.elem_type != ElemType.RUNTIME:
            m[e.name] = [("" if e.elem_type == ElemType.STR64 else 0)] * m.counts[e.count_idx]

    def put(k, v):
        m[k] = v

    names = [nm for nm, _ in LAYERS]

    # ---- drawable ----
    put("art_mesh.ids", names)
    for k in ("parent_part_indices", "parent_deformer_indices"):
        put("art_mesh." + k, [-1] * n)
    put("art_mesh.keyform_binding_band_indices", DRAWABLE_BANDS)
    for k in ("visibles", "enables"):
        put("art_mesh." + k, [True] * n)
    kf_begin, acc = [], 0
    for c in KF_PER:
        kf_begin.append(acc)
        acc += c
    put("art_mesh.keyform_begin_indices", kf_begin)
    put("art_mesh.keyform_counts", KF_PER)
    put("art_mesh.vertex_counts", [NV] * n)
    put("art_mesh.position_index_counts", [NI] * n)
    put("art_mesh.drawable_flags", [4] * n)                 # 4 = 普通可绘制片
    put("art_mesh.mask_begin_indices", [0] * n)
    put("art_mesh.mask_counts", [0] * n)
    put("art_mesh.uv_begin_indices", [i * NF for i in range(n)])
    put("art_mesh.position_index_begin_indices", [i * NI for i in range(n)])

    # ---- 图集 + 网格 + UV ----
    xy, uv, indices = [], [], []
    for row in range(ROWS - 1):
        for col in range(COLS - 1):
            a = row * COLS + col
            b, c, d = a + 1, a + COLS, a + COLS + 1
            indices.extend([a, c, b, b, c, d])

    atlas = Image.new("RGBA", (ATLAS, ATLAS), (0, 0, 0, 0))
    cx, cy = 4, 4
    for i, (nm, fn) in enumerate(LAYERS):
        im = Image.open(SKIN / fn).convert("RGBA")
        w, h = im.size
        assert cx + w + 4 <= ATLAS and cy + h + 4 <= ATLAS, "图集放不下"
        # 边缘外扩 2px, 免得双线性采样在裁切边出现暗边
        padded = Image.fromarray(np.pad(np.array(im), ((2, 2), (2, 2), (0, 0)), mode="edge"))
        atlas.paste(padded, (cx - 2, cy - 2))
        x0, y0 = (0 - ORIGIN_X) / PPU, (0 - ORIGIN_Y) / PPU
        ww, hh = w / PPU, h / PPU
        for r in range(ROWS):
            for c in range(COLS):
                u, v = c / (COLS - 1), r / (ROWS - 1)
                uv.extend([(cx + w * u) / ATLAS, (cy + h * v) / ATLAS])
                xy.extend([x0 + ww * u, y0 + hh * v])
        cy += h + 4
    put("uv.xys", uv)
    put("position_index.indices", indices * n)

    # 逐片、逐关键形生成位置。抬爪 = 该片所有顶点 y 减去 LIFT_PX/PPU。
    # 注意: 每一片的关键形位置块都要各自补到 STRIDE(16 float 对齐), 补在末尾会整体错位。
    kf_xy, opacities, orders, posbegins = [], [], [], []
    for i in range(n):
        for k in range(KF_PER[i]):
            posbegins.append(len(kf_xy))
            pts = xy[i * NF:(i + 1) * NF]
            lift = (LIFT_PX / PPU) if (i > 0 and k == 0) else 0.0
            flat = []
            for j in range(0, NF, 2):
                flat += [pts[j], pts[j + 1] - lift]
            kf_xy += flat + [0.0] * (STRIDE - NF)
            opacities.append(1.0)
            orders.append(float(i))
    put("keyform_position.xys", kf_xy)
    put("art_mesh_keyform.opacities", opacities)
    put("art_mesh_keyform.draw_orders", orders)
    put("art_mesh_keyform.keyform_position_begin_indices", posbegins)

    # ---- 绘制顺序组 ----
    put("draw_order_group.object_begin_indices", [0])
    put("draw_order_group.object_counts", [n])
    put("draw_order_group.object_total_counts", [n])
    put("draw_order_group.min_draw_orders", [0])
    put("draw_order_group.max_draw_orders", [n - 1])
    put("draw_order_group_object.types", [0] * n)
    put("draw_order_group_object.indices", list(range(n)))
    put("draw_order_group_object.group_indices", [-1] * n)

    # ---- 参数 + 关键形绑定 ----
    put("parameter.ids", [x[0] for x in PARAMS])
    put("parameter.min_values", [float(x[1]) for x in PARAMS])
    put("parameter.max_values", [float(x[2]) for x in PARAMS])
    put("parameter.default_values", [float(x[3]) for x in PARAMS])
    put("parameter.repeats", [False] * p)
    put("parameter.decimal_places", [3] * p)
    put("parameter.keyform_binding_begin_indices", list(range(p)))
    put("parameter.keyform_binding_counts", [1] * p)

    band_axes = BANDS
    slot_indices = [a for axes in band_axes for a in axes]
    m.counts[11] = len(slot_indices)
    m.counts[12] = len(band_axes)
    put("keyform_binding_index.indices", slot_indices)
    put("keyform_binding_band.begin_indices", [0])
    starts, acc = [], 0
    for axes in band_axes:
        starts.append(acc)
        acc += len(axes)
    put("keyform_binding_band.begin_indices", starts)
    put("keyform_binding_band.counts", [len(a) for a in band_axes])

    keys, kbeg = [], []
    for x in PARAMS:
        kbeg.append(len(keys))
        keys += [float(v) for v in x[4]]
    put("keyform_binding.keys_begin_indices", kbeg)
    put("keyform_binding.keys_counts", [len(x[4]) for x in PARAMS])

    # ---- Cubism 4.2 的补充表: 不写这几张表 Core 5 会拒载 ----
    extra = []
    for slot in range(101, 137):
        typ = ElemType.F32 if slot in list(range(108, 114)) + [135, 136] else ElemType.I32
        extra.append(SectionEntry("v42.%d" % slot, typ, -1, 64))
        m["v42.%d" % slot] = []
    extra[1] = SectionEntry("v42.102", ElemType.RUNTIME, 5, 64)
    m.header.version = 4
    m._build_layout = lambda: list(SECTION_LAYOUT) + extra

    colors = N_KF + 3                                    # 每个关键形一条 + 3 条固定
    m.counts.extend([colors, colors] + [0] * 7)
    put("v42.103", [len(keys) + o for o in kbeg])
    put("v42.104", [len(x[4]) for x in PARAMS])
    put("keys.values", keys + keys)
    m.counts[14] = len(keys) * 2
    put("v42.106", [0])
    put("v42.107", [b + 3 for b in kf_begin])
    for slot in range(108, 111):
        put("v42.%d" % slot, [1.0] * colors)
    for slot in range(111, 114):
        put("v42.%d" % slot, [0.0] * colors)
    for slot in range(114, 117):
        put("v42.%d" % slot, [0] * p)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    m.to_file(str(OUT_DIR / "Moon.moc3"))
    atlas.save(OUT_DIR / "texture_00.png")

    # ---- 动作文件: BongoCat 是靠"播放动作"来拍手的(官方模型的 CAT_motion 组),
    #      没有动作的模型在它里面就会愣着不动。这里生成两个"拍一下"的动作, 曲线直接
    #      驱动我们自己的手部参数(0=抬起 1=拍下), 两个动作分别拍左右手, 它随机取用。
    def slap_motion(fname, left_down, right_down):
        def curve(pid, own):
            other = 1.0 - own * 0.0
            v0, v1, v2 = (0.0, own, 0.0) if pid == left_down else (0.0, own, 0.0)
            return {"Target": "Parameter", "Id": pid, "Segments": [0.0, v0, 0, 0.16, v1, 0, 0.42, v2]}
        curves = [curve("Param", 1.0 if left_down else 0.15),
                  curve("Param2", 1.0 if right_down else 0.15),
                  curve("ParamAngleZ", 1.2 if left_down else -1.2)]
        segs = sum((len(c["Segments"]) - 2) // 3 for c in curves)
        doc = {"Version": 3,
               "Meta": {"Duration": 0.42, "Fps": 30.0, "Loop": False,
                        "AreBeziersRestricted": True, "CurveCount": len(curves),
                        "TotalSegmentCount": segs, "TotalPointCount": segs + len(curves),
                        "UserDataCount": 0, "TotalUserDataSize": 0},
               "Curves": curves, "UserData": []}
        (OUT_DIR / fname).write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return fname

    slap_left = slap_motion("live2d_motion1.motion3.json", True, False)
    slap_right = slap_motion("live2d_motion2.motion3.json", False, True)
    motions = {g: [{"File": f, "FadeInTime": 0, "FadeOutTime": 0} for f in (slap_left, slap_right)]
               for g in ("CAT_motion", "CAT_motion_lock")}
    (OUT_DIR / "Moon.model3.json").write_text(json.dumps({
        "Version": 3,
        "FileReferences": {"Moc": "Moon.moc3", "Textures": ["texture_00.png"], "Motions": motions},
        "Groups": [],
    }, indent=2), encoding="utf-8")
    print("已写出:", OUT_DIR)
    for f in sorted(OUT_DIR.iterdir()):
        print("   %8.1f KB  %s" % (f.stat().st_size / 1024, f.name))
    return OUT_DIR


def verify(model_dir: Path):
    """用 live2d-py(官方 Cubism Core)真正加载并渲染一帧, 跟原画比对。"""
    os.environ.setdefault("QT_OPENGL", "desktop")
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat, QImage
    from PySide6.QtWidgets import QApplication
    from OpenGL import GL

    app = QApplication.instance() or QApplication(sys.argv)
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    surf = QOffscreenSurface()
    surf.setFormat(fmt)
    surf.create()
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    ctx.create()
    ctx.makeCurrent(surf)

    import live2d
    live2d.init()
    live2d.glInit()
    m = live2d.Model()
    m.LoadModelJson(str(model_dir / "Moon.model3.json"))
    print("Core 加载成功; 参数:", m.GetParamIds())

    W, H = CANVAS_W, CANVAS_H
    fbo = GL.glGenFramebuffers(1)
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, W, H, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
    GL.glViewport(0, 0, W, H)
    m.Resize(W, H)
    m.SetAutoBreath(False)
    m.SetAutoBlink(False)

    def grab():
        for _ in range(2):
            m.Update(1 / 60.0)
        live2d.clearBuffer(0, 0, 0, 0)
        m.Draw()
        GL.glFinish()
        buf = GL.glReadPixels(0, 0, W, H, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        return np.frombuffer(buf, np.uint8).reshape(H, W, 4)[::-1].copy()

    arr = grab()
    n_on = (arr[..., 3] > 8).sum()
    print("渲染出来非透明像素: %d" % n_on)

    # 与皮肤场景板 + 两只手拼起来的原图对比
    ref = Image.open(SKIN / "bg.png").convert("RGBA")
    for _, fn in LAYERS[1:]:
        ref.alpha_composite(Image.open(SKIN / fn).convert("RGBA"))
    ref_a = np.array(ref)
    both = (arr[..., 3] > 128) & (ref_a[..., 3] > 128)
    if both.sum():
        d = np.abs(arr[..., :3].astype(np.int16) - ref_a[..., :3].astype(np.int16)).max(2)[both]
        print("与原画重合区: %d px, 平均差 %.2f, 差>30 的占 %.2f%%"
              % (both.sum(), d.mean(), (d > 30).mean() * 100))
    # 抬爪测试: 把两个参数都拉到 1, 爪子应上移 LIFT_PX, 露出背后的桌面/键盘
    m.SetParamById("CatParamLeftHandDown", 1.0)
    m.SetParamById("CatParamRightHandDown", 1.0)
    up = grab()
    ya = np.nonzero((arr[..., 3] > 128))[0]
    yb = np.nonzero((up[..., 3] > 128))[0]
    if len(ya) and len(yb):
        print("抬爪前后不透明像素上边界: %d -> %d (应减少约 %.0f px)"
              % (ya.min(), yb.min(), LIFT_PX))
    Image.fromarray(up[:, :, :], "RGBA").save(ROOT / "build" / "moc3_lifted.png")
    m.SetParamById("CatParamLeftHandDown", 0.0)
    m.SetParamById("CatParamRightHandDown", 0.0)

    out = ROOT / "build" / "moc3_verify.png"
    sheet = Image.new("RGBA", (W * 2 + 8, H), (245, 245, 248, 255))
    a = Image.new("RGBA", (W, H), (245, 245, 248, 255)); a.alpha_composite(ref)
    b = Image.new("RGBA", (W, H), (245, 245, 248, 255)); b.alpha_composite(Image.fromarray(arr, "RGBA"))
    sheet.paste(a, (0, 0)); sheet.paste(b, (W + 8, 0))
    sheet.convert("RGB").resize(((W * 2 + 8) // 2, H // 2), Image.LANCZOS).save(out)
    print("对比图 -> %s  (左=原画 右=Core 渲染)" % out)


if __name__ == "__main__":
    d = build()
    if "--verify" in sys.argv:
        verify(d)
