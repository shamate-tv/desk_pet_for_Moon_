# -*- coding: utf-8 -*-
"""把 build/ 里的验收图导出成仓库用的 preview/ 目录(build/ 被 .gitignore 忽略, 不能当图床)。
输出全部为 ASCII 文件名, 体积做了压缩, 供 README 引用。
"""
import os
from PIL import Image

SRC = "build"
DST = "preview"
os.makedirs(DST, exist_ok=True)


def export(src, dst, scale=1.0, quality=None, crop=None):
    p = os.path.join(SRC, src)
    if not os.path.exists(p):
        print("跳过(不存在):", src)
        return
    im = Image.open(p)
    if crop:
        im = im.crop(crop)
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                       Image.LANCZOS)
    out = os.path.join(DST, dst)
    if quality:
        im.convert("RGB").save(out, quality=quality, optimize=True)
    else:
        im.save(out, optimize=True)
    print("%-22s <- %-24s %6.0f KB" % (dst, src, os.path.getsize(out) / 1024))


def export_gif():
    """动图单独做小一点, 不然仓库里放个 2MB 的 gif 太重。"""
    import sys
    sys.argv = ["x"]
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pg", os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview_gif.py"))
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)
    pg.SCALE = 0.38
    pg.main()
    im = Image.open(os.path.join(SRC, "preview.gif"))
    frames = []
    for i in range(im.n_frames):
        im.seek(i)
        frames.append(im.convert("RGB").quantize(colors=48, method=Image.MEDIANCUT))
    out = os.path.join(DST, "typing.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=55, loop=0, disposal=2)
    print("%-22s <- %-24s %6.0f KB" % ("typing.gif", "preview.gif", os.path.getsize(out) / 1024))


if __name__ == "__main__":
    export("preview_sheet.png", "typing.jpg", 0.85, 88)
    export("selftest.png", "states.jpg", 0.70, 88)
    export("review_matte.png", "matte.jpg", 0.80, 90)
    export("review_rotate.png", "hand-rotate.jpg", 0.85, 88)
    export("review_lid.png", "blink.png", 1.0)
    # 桌面实拍: 裁掉聊天窗口, 只留桌宠 + 任务栏
    export("exe_screen.png", "desktop.jpg", 0.62, 88, crop=(190, 95, 735, 840))
    export_gif()
    for old in ("typing.png", "states.png", "matte.png", "hand-rotate.png"):
        f = os.path.join(DST, old)
        if os.path.exists(f):
            os.remove(f)
    total = sum(os.path.getsize(os.path.join(DST, f)) for f in os.listdir(DST))
    print("preview/ 合计 %.2f MB" % (total / 1048576))
