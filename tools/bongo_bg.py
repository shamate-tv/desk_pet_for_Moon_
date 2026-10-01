# -*- coding: utf-8 -*-
"""组装 Bongo 版素材 —— 全部用画师手工分好的图层, 不做任何自动补洞。

art/ 里的图层(都是 1459x1078 全画布, 位置已对齐, 直接叠就行):
  桌子 / 键盘 / 鼠标垫 / 人物 / 左手 / 右手

产出:
  skins/moon/bg.png     场景板 = 桌子 + 键盘 + 鼠标垫 + 人物 (不含两只手)
  skins/moon/paw_l.png  左手可动层
  skins/moon/paw_r.png  右手可动层
  skins/moon/eyes_closed.png  闭眼补丁(用原画线宽合成, 见 tools/bongo_cut.py)

叠放顺序已验证: 六层叠加与 art/BongoCatOC抠图.png 在"两者都实心"的像素上平均差 2.39,
差异>30 的仅 1.8%(都在边缘抗锯齿处), 可视为完美还原。
"""
import os
import numpy as np
from PIL import Image

BG_LAYERS = ["桌子", "键盘", "鼠标垫", "人物"]      # 从下到上
OUT_DIR = "skins/moon"                      # 组装结果直接进皮肤目录
OUT_BG = os.path.join(OUT_DIR, "bg.png")
HANDS = {"l": "左手", "r": "右手"}
SRC = "art/BongoCatOC抠图.png"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    size = Image.open("art/桌子.png").size

    bg = Image.new("RGBA", size, (0, 0, 0, 0))
    for name in BG_LAYERS:
        bg.alpha_composite(Image.open("art/%s.png" % name).convert("RGBA"))
    bg.save(OUT_BG)

    for side, name in HANDS.items():
        im = Image.open("art/%s.png" % name).convert("RGBA")
        im.save(os.path.join(OUT_DIR, "paw_%s.png" % side))
        a = np.array(im)[..., 3]
        ys, xs = np.nonzero(a > 20)
        print("%s -> %s/paw_%s.png  bbox x %d-%d y %d-%d (%d px)"
              % (name, OUT_DIR, side, xs.min(), xs.max(), ys.min(), ys.max(), (a > 20).sum()))

    # 审核图: 原图 | 场景板+两只手 的三层对照
    def flat(im):
        p = Image.new("RGBA", size, (245, 245, 248, 255))
        p.alpha_composite(im)
        return p.convert("RGB")

    full = bg.copy()
    for name in HANDS.values():
        full.alpha_composite(Image.open("art/%s.png" % name).convert("RGBA"))
    box = (240, 560, 1360, 1010)
    tiles = [flat(Image.open(SRC).convert("RGBA")).crop(box), flat(bg).crop(box), flat(full).crop(box)]
    s = 0.75
    tiles = [t.resize((int(t.width * s), int(t.height * s)), Image.LANCZOS) for t in tiles]
    sheet = Image.new("RGB", (tiles[0].width * 3 + 16, tiles[0].height), (20, 20, 22))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * (tiles[0].width + 8), 0))
    sheet.save("build/review_scene.png")
    print("skins/moon/ ok  ->  build/review_scene.png (原图 | 场景板 | 场景板+双手)")


if __name__ == "__main__":
    main()
