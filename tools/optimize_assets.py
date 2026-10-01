# -*- coding: utf-8 -*-
"""无损瘦身: 去掉 PNG 里的 Photoshop 元数据(dpi/XMP/chromaticity) 并重新压缩。

这些图层从 PS 导出时带了几 MB 的 XMP 编辑历史, 但对渲染毫无用处。
逐像素校验, 保证画面 0 损失; 只改文件大小。

用法: python tools/optimize_assets.py [目录...]      (默认 art assets assets_halfbody)
"""
import os
import sys
import numpy as np
from PIL import Image

DEFAULT_DIRS = ["art", "assets", "assets_halfbody"]


def optimize(path):
    before = os.path.getsize(path)
    im = Image.open(path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    src = np.array(im)
    tmp = path + ".tmp.png"
    im.save(tmp, optimize=True)                 # 不带 info= 即丢弃元数据
    out = Image.open(tmp)
    if out.mode != "RGBA":
        out = out.convert("RGBA")
    dst = np.array(out)
    if src.shape != dst.shape or not np.array_equal(src, dst):
        os.remove(tmp)
        return before, before, False           # 像素有变, 放弃
    os.replace(tmp, path)
    return before, os.path.getsize(path), True


def main(dirs):
    tb = ta = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                if not f.lower().endswith(".png"):
                    continue
                p = os.path.join(root, f)
                b, a, ok = optimize(p)
                if not ok:
                    print("  ! 跳过(像素会变):", p)
                    continue
                tb += b
                ta += a
                if b - a > 20 * 1024:
                    print("  %-34s %6.1f MB -> %5.2f MB" % (p, b / 1048576, a / 1048576))
    print("\n合计: %.1f MB -> %.1f MB  (省下 %.1f MB, 全部逐像素校验无损)"
          % (tb / 1048576, ta / 1048576, (tb - ta) / 1048576))


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_DIRS)
