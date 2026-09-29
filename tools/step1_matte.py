# -*- coding: utf-8 -*-
"""整图抠像: 把 角色 + 帽子羽毛 + 椅子 + 桌子 + 笔记本 从亮色墙面里切出来。
输出: assets/sprite.png (RGBA) + build/review_matte.png

三层策略:
  1. 手工多边形给出"保留区域"(硬约束), 解决黑色西装配深色椅子的低对比度边界 ——
     椅子按场景道具保留, 只抠掉左上/右上那片亮墙。
  2. 多边形内/外 + "明亮低饱和=墙" 作为 GrabCut 的硬种子, 让 GrabCut 去吸附真实边缘。
  3. 帽子羽毛一半是白色, 和亮墙同色, GrabCut 无解 —— 单独用局部对比度找它的描边
     (比局部背景暗 或 高饱和紫), 取连通域并填内部孔洞, 再用手工凸包限制作用范围。
"""
import os
import cv2
import numpy as np
from PIL import Image

SRC = os.path.join("art", "base.jpg")
OUT_DIR = "assets"
REVIEW_DIR = "build"

# 帽子羽毛: 局部掩膜的作用范围(比实际轮廓外扩 ~5px)
FEATHER_HULL = np.array([
    (560, -2), (572, 25), (578, 60), (580, 95), (578, 125), (570, 148),
    (556, 160), (532, 169), (506, 176), (486, 173), (462, 167), (446, 158), (436, 146),
    (446, 126), (462, 104), (478, 84), (496, 60), (514, 36), (534, 12),
], np.int32)
FEATHER_BOX = (420, 0, 620, 200)
FEATHER_SEED = (530, 60)                  # 羽毛内部一点(全图坐标)

# 保留区域多边形(顺时针)
KEEP_POLY = np.array([
    (400, 58), (450, 74), (487, 110),                     # 帽冠右缘
    (500, 60), (516, 20), (546, -25), (596, 0),           # 羽毛区域放宽(真实边界由局部掩膜定)
    (612, 60), (600, 140), (556, 186), (520, 198),
    (560, 204), (660, 216), (768, 240),                   # 椅子靠背上缘(以上是亮墙)
    (768, 1123), (0, 1123), (0, 856),
    (22, 866), (60, 892), (86, 878), (52, 846),           # 笔记本左上 -> 袖口
    (38, 800), (54, 752), (84, 692), (116, 626), (156, 566),   # 袖子左轮廓
    (204, 528), (168, 512),
    (106, 490), (80, 458), (58, 416), (42, 366), (26, 312),    # 左侧头发
    (12, 258), (14, 214), (28, 166), (52, 130), (100, 100),    # 帽檐/飘带
    (146, 68), (194, 40), (248, 22), (300, 20), (356, 30),
], np.int32)


def feather_mask(img):
    """羽毛局部掩膜: 描边(比局部背景暗) 或 高饱和紫 -> 取连通域 -> 填内部孔洞。"""
    x0, y0, x1, y1 = FEATHER_BOX
    crop = img[y0:y1, x0:x1]
    L = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32)
    sat = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)[..., 1].astype(np.float32)
    bg = cv2.GaussianBlur(L, (0, 0), 22)
    m = ((L < bg - 8) | (sat > 42)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, _st, _c = cv2.connectedComponentsWithStats(m, 8)
    sx, sy = FEATHER_SEED[0] - x0, FEATHER_SEED[1] - y0
    k = lab[sy, sx]
    if k == 0:
        return None
    m2 = np.where(lab == k, 255, 0).astype(np.uint8)
    ff = m2.copy()
    cv2.floodFill(ff, np.zeros((m2.shape[0] + 2, m2.shape[1] + 2), np.uint8), (0, 0), 255)
    m3 = cv2.bitwise_or(m2, cv2.bitwise_not(ff))
    full = np.zeros(img.shape[:2], np.uint8)
    full[y0:y1, x0:x1] = m3
    return full


def build_sprite():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    img = np.array(Image.open(SRC).convert("RGB"))
    h, w = img.shape[:2]
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)

    poly = np.zeros((h, w), np.uint8)
    cv2.fillPoly(poly, [KEEP_POLY], 255)
    poly_in = cv2.erode(poly, np.ones((9, 9), np.uint8))
    poly_out = cv2.dilate(poly, np.ones((5, 5), np.uint8))

    hull = np.zeros((h, w), np.uint8)
    cv2.fillPoly(hull, [FEATHER_HULL], 255)

    gc = np.full((h, w), cv2.GC_PR_FGD, np.uint8)
    gc[poly == 0] = cv2.GC_PR_BGD
    gc[poly_out == 0] = cv2.GC_BGD
    gc[poly_in > 0] = cv2.GC_FGD

    # 明亮低饱和 = 墙 (羽毛凸包内豁免, 因为羽毛本身是白的)
    wall = ((val > 205) & (sat < 45)).astype(np.uint8) * 255
    wall = cv2.dilate(wall, np.ones((7, 7), np.uint8))
    wall[poly_in > 0] = 0
    wall[hull > 0] = 0
    gc[wall > 0] = cv2.GC_BGD

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)

    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    m[poly == 0] = 0

    # 羽毛: 凸包内由局部掩膜权威决定(掩膜外一律透明)
    fm = feather_mask(img)
    if fm is not None:
        m[hull > 0] = np.where(fm[hull > 0] > 0, 255, 0)
    # 羽毛右上那片亮墙: 凸包之外 + 明亮低饱和 -> 透明
    # (那里落在 poly_in 硬前景里, 靠 GrabCut 是抠不掉的)
    kill = np.zeros((h, w), bool)
    kill[0:200, 500:620] = (((val > 195) & (sat < 48))[0:200, 500:620] &
                            (hull[0:200, 500:620] == 0))
    m[kill] = 0
    m[poly == 0] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, 4]))
        m = np.where(lab == k, 255, 0).astype(np.uint8)

    alpha = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.4) / 255.0
    alpha = np.clip((alpha - 0.35) / (0.72 - 0.35), 0, 1) ** 1.15

    # 去白边
    bg_col = np.array([246.0, 246.0, 250.0])
    a3 = alpha[..., None]
    f = img.astype(np.float32)
    edge = (alpha > 0.02) & (alpha < 0.98)
    decon = (f - (1 - a3) * bg_col) / np.maximum(a3, 0.25)
    f = np.where(edge[..., None], np.clip(decon, 0, 255), f)

    rgba = np.dstack([f, alpha * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(os.path.join(OUT_DIR, "sprite.png"))

    chk = np.zeros((h, w, 3), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    chk[...] = np.where(((yy // 24 + xx // 24) % 2)[..., None] == 0, 205, 150)
    pre = (f * a3 + chk * (1 - a3)).astype(np.uint8)
    cont, _ = cv2.findContours((alpha * 255).astype(np.uint8), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_NONE)
    prev = cv2.cvtColor(pre, cv2.COLOR_RGB2BGR).copy()
    cv2.drawContours(prev, cont, -1, (0, 0, 255), 1)
    Image.fromarray(cv2.cvtColor(prev, cv2.COLOR_BGR2RGB)).save(
        os.path.join(REVIEW_DIR, "review_matte.png"))
    print("sprite.png ok, 不透明像素占比 %.3f" % (alpha > 0.5).mean())
    return rgba


if __name__ == "__main__":
    build_sprite()
