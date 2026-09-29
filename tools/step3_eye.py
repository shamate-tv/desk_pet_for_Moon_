# -*- coding: utf-8 -*-
"""眨眼层: 生成"闭眼"补丁。
输出: assets/lid.png (全画布 RGBA)

做法:
  1. 只把"紫色虹膜"(B-R 明显偏大)和内侧睫毛线判为待填区域 —— 横穿眼睛那缕头发是
     中性深色, 不会进洞, 于是眨眼时它自然保留。
  2. inpaint 填成皮肤, 再把色度拉向周围真实皮肤色(保留明暗), 消除睫毛的黑色晕染。
  3. 用贝塞尔弧重画"闭眼睫毛线", 外眼角的长睫毛沿用原图(不在补丁范围内)。
"""
import os
import cv2
import numpy as np
from PIL import Image

SPRITE = os.path.join("assets", "sprite.png")
BOX = (325, 335, 415, 396)
LASH_BAND = (330, 336, 394, 353)        # 内侧上睫毛线(全图坐标) 需要抹掉重画
EYE_OPEN = np.array([                    # 眼睛开口(含睫毛线)多边形, 全图坐标
    (332, 366), (340, 356), (355, 349), (375, 346), (392, 348), (401, 356),
    (397, 369), (384, 378), (365, 382), (348, 378), (338, 372)], np.int32)
NEW_LASH = [(334, 368), (366, 381), (403, 356)]   # 闭眼时睫毛线贴着下眼睑


def main():
    sprite = np.array(Image.open(SPRITE).convert("RGBA"))
    H, W = sprite.shape[:2]
    x0, y0, x1, y1 = BOX
    crop = sprite[y0:y1, x0:x1, :3].copy()
    ch, cw = crop.shape[:2]
    f = crop.astype(np.int16)
    R, G, B = f[..., 0], f[..., 1], f[..., 2]
    mx = f.max(2)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

    # 洞 = 眼睛开口多边形 + 紫色虹膜 + 开口附近的深色(睫毛线/横穿的头发)
    hole = np.zeros((ch, cw), np.uint8)
    cv2.fillPoly(hole, [EYE_OPEN - np.array([x0, y0])], 255)
    violet = ((B - R > 12) & (mx > 75)).astype(np.uint8) * 255
    violet = cv2.morphologyEx(violet, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    near9 = cv2.dilate(hole, np.ones((9, 9), np.uint8))
    dark = (gray < 140).astype(np.uint8) * 255
    hole = cv2.bitwise_or(hole, cv2.bitwise_and(violet, near9))
    hole = cv2.bitwise_or(hole, cv2.bitwise_and(dark, near9))
    hole = cv2.dilate(hole, np.ones((3, 3), np.uint8))
    hole = cv2.morphologyEx(hole, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    hole[:2, :] = hole[-2:, :] = 0
    hole[:, :2] = hole[:, -2:] = 0

    # --- 按列垂直插值填充: 用眼睛上方(眉下)与下方(颊)的干净皮肤色拉出眼皮 ---
    warm = (R - B > 6) & (mx > 140)
    ys_all = np.arange(ch)[:, None]

    def clean_row(y_lo, y_hi):
        """返回该行带内每列的干净肤色(中值), 并做横向平滑"""
        rows = crop[y_lo - y0:y_hi - y0].astype(np.float32)
        mrows = warm[y_lo - y0:y_hi - y0]
        gp = np.where(mrows[..., None], rows, np.nan)
        with np.errstate(all="ignore"):
            col = np.nanmedian(gp, axis=0)
        bad = np.isnan(col[:, 0])
        if bad.any():
            col[bad] = np.nanmedian(col, axis=0)
        k = np.ones((9, 1), np.float32) / 9.0
        col = cv2.filter2D(col.reshape(1, cw, 3), -1, k.reshape(1, 9, 1),
                           borderType=cv2.BORDER_REPLICATE).reshape(cw, 3)
        return col

    top = clean_row(324, 333)[None, :, :]        # 眉下皮肤
    bot = clean_row(385, 394)[None, :, :]        # 下眼睑下方/颊
    t = np.clip((ys_all + y0 - y0) / float(ch - 1), 0, 1)[:, :, None]
    skin_fill = (top * (1 - t) + bot * t).astype(np.float32)

    a = cv2.GaussianBlur(hole, (0, 0), 1.6)[..., None].astype(np.float32) / 255.0
    lid = skin_fill * a + crop.astype(np.float32) * (1 - a)

    # 重画闭眼睫毛线
    p0, p1, p2 = [np.array([p[0] - x0, p[1] - y0], np.float32) for p in NEW_LASH]
    ts = np.linspace(0, 1, 80)
    pts = ((1 - ts) ** 2)[:, None] * p0 + (2 * (1 - ts) * ts)[:, None] * p1 + (ts ** 2)[:, None] * p2
    line = np.zeros((ch, cw), np.uint8)
    cv2.polylines(line, [pts.astype(np.int32)], False, 255, 2, cv2.LINE_AA)
    line = cv2.GaussianBlur(line, (3, 3), 0.7)
    dark_px = crop[((gray < 110).astype(np.uint8) * 255 > 0)]
    lash_col = np.median(dark_px, 0) if len(dark_px) else np.array([70, 50, 72])
    la = (line.astype(np.float32) / 255.0) * 0.88
    lid = lid * (1 - la[..., None]) + lash_col * la[..., None]
    lid = np.clip(lid, 0, 255).astype(np.uint8)

    patch_a = np.clip((cv2.GaussianBlur(cv2.dilate(hole, np.ones((5, 5), np.uint8)),
                                        (0, 0), 1.6).astype(np.float32) / 255.0 - 0.1) / 0.6, 0, 1)
    lid_alpha = np.zeros((H, W), np.uint8)
    lid_alpha[y0:y1, x0:x1] = (patch_a * 255).astype(np.uint8)
    lid_full = np.zeros((H, W, 3), np.uint8)
    lid_full[y0:y1, x0:x1] = lid
    Image.fromarray(np.dstack([lid_full, lid_alpha]), "RGBA").save("assets/lid.png")

    open_eye = sprite[y0:y1, x0:x1, :3]
    closed = (lid.astype(np.float32) * patch_a[..., None] +
              open_eye.astype(np.float32) * (1 - patch_a[..., None])).astype(np.uint8)
    strip = np.hstack([open_eye, closed]).astype(np.uint8)
    big = Image.fromarray(strip).resize((cw * 8, ch * 4), Image.LANCZOS)
    small = Image.fromarray(strip).resize((cw * 2, ch), Image.LANCZOS)
    canvas = Image.new("RGB", (cw * 8, ch * 4 + ch + 8), (255, 255, 255))
    canvas.paste(big, (0, 0))
    canvas.paste(small.resize((cw * 2, ch), Image.LANCZOS), (0, ch * 4 + 8))
    canvas.save("build/review_lid.png")
    print("lid.png ok -> build/review_lid.png")


if __name__ == "__main__":
    main()
