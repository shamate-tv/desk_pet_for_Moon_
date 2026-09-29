# -*- coding: utf-8 -*-
"""把 build/ 里的验收图导出成仓库用的 preview/ 目录(build/ 被 .gitignore 忽略)。
输出全部 ASCII 文件名 + 压过体积, 供 README 引用。
"""
import os
import subprocess
import sys
from PIL import Image

SRC, DST = "build", "preview"
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
    print("%-18s <- %-24s %6.0f KB" % (dst, src, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    subprocess.run([sys.executable, os.path.join("tools", "preview_bongo.py")], check=True)
    export("preview_bongo_sheet.png", "typing.jpg", 0.80, 88)   # 打字分帧
    export("selftest_bongo.png", "states.jpg", 0.62, 88)        # 五个状态
    export("review_bongo.png", "paw-dive.jpg", 0.80, 88)        # 爪子下砸 + 补洞检查
    export("review_bongo_eyes.png", "blink.png", 1.0)           # 睁眼/闭眼
    export("bongo_live.png", "desktop.jpg", 0.60, 88, crop=(40, 20, 700, 500))
    # 主预览动图: 重新压成仓库用尺寸
    im = Image.open(os.path.join(SRC, "preview_bongo.gif"))
    frames = []
    for i in range(0, im.n_frames, 3):          # 隔帧取, 30fps 足够, 体积减半
        im.seek(i)
        frames.append(im.convert("RGB").quantize(colors=40, method=Image.MEDIANCUT))
    frames[0].save(os.path.join(DST, "typing.gif"), save_all=True, append_images=frames[1:],
                   duration=int(im.info.get("duration", 17)) * 3, loop=0, disposal=2)
    print("%-18s <- %-24s %6.0f KB" % ("typing.gif", "preview_bongo.gif",
                                       os.path.getsize(os.path.join(DST, "typing.gif")) / 1024))
    for old in ("hand-rotate.jpg", "matte.jpg"):
        f = os.path.join(DST, old)
        if os.path.exists(f):
            os.remove(f)
    total = sum(os.path.getsize(os.path.join(DST, f)) for f in os.listdir(DST))
    print("preview/ 合计 %.2f MB" % (total / 1048576))
