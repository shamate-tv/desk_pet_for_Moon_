# -*- coding: utf-8 -*-
"""组装 Bongo 版的完整场景 (assets/bg.png) —— 爪子可以自由移动, 让开的地方要有东西。

素材分工:
  art/BongoCatOC抠图.png  全图(键盘、桌沿、白桌面都在这里)
  art/人物.png            画师分出来的角色(左手已经被挖掉)
  art/鼠标垫.png          画师分出来的鼠标垫
  art/左手.png            画师分出来的左手(同时就是可动层)

左手背后那块用画师的三层拼回来(干净); 右爪没有对应图层, 仍用自动填充。
"""
import cv2
import numpy as np
import scipy.ndimage as ndi
from PIL import Image

ORIG = "art/BongoCatOC抠图.png"
CHAR, PAD, HAND = "art/人物.png", "art/鼠标垫.png", "art/左手.png"
KB = "art/键盘.png"          # 画师扣好的键盘(右手压住的那块也已补好)
OUT_BG = "assets/bg.png"
OUT_HAND = "assets/paw_l.png"


def load(p):
    a = np.array(Image.open(p).convert("RGBA"))
    return a[..., :3], a[..., 3]


def main():
    org_rgb, org_a = load(ORIG)
    ch_rgb, ch_a = load(CHAR)
    pd_rgb, pd_a = load(PAD)
    hd_rgb, hd_a = load(HAND)
    kb_rgb, kb_a = load(KB)
    h, w = org_a.shape
    plate = org_rgb.copy()

    # ---- 1) 左手背后: 用画师分好的图层拼回来 ----
    #    优先"人物", 其次"鼠标垫", 都没有就保留原像素(白桌面/桌沿)
    hd_a2 = cv2.GaussianBlur(cv2.dilate(hd_a, np.ones((5, 5), np.uint8)), (0, 0), 1.2)
    hand = np.maximum(hd_a, hd_a2).astype(np.float32) / 255.0
    fill = plate.copy()
    take = ch_a >= 128                      # 人物在最前面, 其次键盘, 再其次鼠标垫
    fill[take] = ch_rgb[take]
    take2 = (~take) & (kb_a >= 128)
    fill[take2] = kb_rgb[take2]
    take3 = (~take) & (~take2) & (pd_a >= 128)
    fill[take3] = pd_rgb[take3]
    a3 = hand[..., None]
    plate = (fill.astype(np.float32) * a3 + plate.astype(np.float32) * (1 - a3)).astype(np.uint8)

    # ---- 2) 右爪背后: 同样用画师的图层拼(人物 -> 键盘 -> 鼠标垫 -> 原像素) ----
    pr_a = np.array(Image.open("assets/paw_r.png").convert("RGBA"))[..., 3]
    pr_a2 = cv2.GaussianBlur(cv2.dilate(pr_a, np.ones((5, 5), np.uint8)), (0, 0), 1.2)
    rr = (np.maximum(pr_a, pr_a2).astype(np.float32) / 255.0)[..., None]
    plate = (fill.astype(np.float32) * rr + plate.astype(np.float32) * (1 - rr)).astype(np.uint8)
    Image.fromarray(np.dstack([plate, org_a]), "RGBA").save(OUT_BG)

    # ---- 3) 左手层直接用画师那张(比我自动描的干净) ----
    Image.fromarray(np.dstack([hd_rgb, hd_a]), "RGBA").save(OUT_HAND)

    ys, xs = np.nonzero(hd_a > 20)
    print("左手层 bbox: x %d-%d y %d-%d  (%d px)" % (xs.min(), xs.max(), ys.min(), ys.max(),
                                                (hd_a > 20).sum()))

    # ---- 审核图: 原图 | 场景板(无手) ----
    def flat(rgb, al):
        p = Image.new("RGBA", (w, h), (245, 245, 248, 255))
        p.alpha_composite(Image.fromarray(np.dstack([rgb, al])))
        return p.convert("RGB")

    box = (240, 560, 1120, 1010)
    a_img = flat(org_rgb, org_a).crop(box)
    b_img = flat(plate, org_a).crop(box)
    s = 0.94
    a_img = a_img.resize((int(a_img.width * s), int(a_img.height * s)), Image.LANCZOS)
    b_img = b_img.resize((int(b_img.width * s), int(b_img.height * s)), Image.LANCZOS)
    sheet = Image.new("RGB", (a_img.width * 2 + 8, a_img.height), (20, 20, 22))
    sheet.paste(a_img, (0, 0))
    sheet.paste(b_img, (a_img.width + 8, 0))
    sheet.save("build/review_scene.png")
    print("assets/bg.png + assets/paw_l.png ok  ->  build/review_scene.png (左=原图 右=无手的场景)")


if __name__ == "__main__":
    main()
