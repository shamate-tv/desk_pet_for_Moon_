# -*- coding: utf-8 -*-
"""切出"打字的手"。
输出: assets/hand.png  (全画布 RGBA, 只有手不透明; 腕部 alpha 渐隐到 0, 便于旋转时无缝)
      assets/base.png  (全画布 RGBA, 手背后已补洞, 供抬手动作用)

关键: 皮肤是暖调(R>B), 笔记本机身/键盘是冷调(B>R), 紫色袖子/指甲是高饱和紫。
      用 R-B 色差做种子比 GrabCut 盲猜稳得多。
动作用"绕腕关节旋转"(见 pet/main.py), 手腕不动 => 不会有撕裂接缝。
"""
import os
import cv2
import numpy as np
from PIL import Image

SPRITE = os.path.join("assets", "sprite.png")
BOX = (170, 900, 512, 1105)      # 手部裁剪框
PIVOT = (470, 1030)              # 腕关节(全图坐标) —— 旋转轴
FADE_X0, FADE_X1 = 466, 502      # 全图坐标: 手的 alpha 从这里开始渐隐, 让位给袖子


def hand_mask(crop_rgb):
    h, w = crop_rgb.shape[:2]
    f = crop_rgb.astype(np.int16)
    R, G, B = f[..., 0], f[..., 1], f[..., 2]
    mx, mn = f.max(2), f.min(2)
    sat = mx - mn
    warm = R - B                       # >0 偏暖(皮肤), <0 偏冷(机身/紫)

    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc[(warm > 8) & (mx > 145) & (sat < 62)] = cv2.GC_FGD            # 皮肤
    gc[(warm < -6)] = cv2.GC_BGD                                       # 机身/键盘/深色
    gc[(warm < -20) & (sat > 45)] = cv2.GC_FGD                         # 指甲(紫色)

    xs = np.arange(w)[None, :] + BOX[0]
    ys = np.arange(h)[:, None] + BOX[1]
    sleeve = (warm < -20) & (sat > 42) & (xs > 470)                    # 紫袖子
    gc[sleeve] = cv2.GC_BGD
    gc[(xs > 430) & (xs < 500) & (ys > 965) & (ys < 1075)] = cv2.GC_FGD  # 手链/腕部
    gc[mx < 88] = cv2.GC_BGD

    bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr, gc, (14, 20, w - 30, h - 30), np.zeros((1, 65)), np.zeros((1, 65)),
                6, cv2.GC_INIT_WITH_MASK)
    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    m[:, xs[0] - BOX[0] > 500 - BOX[0]] = 0                            # 硬性截断袖子
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, 4]))
        m = np.where(lab == k, 255, 0).astype(np.uint8)
    return cv2.dilate(m, np.ones((3, 3), np.uint8), 1)


def fill_hole(crop_rgb, hole, keep_from_x):
    """补洞: inpaint 后用周围材质的色度覆盖掉补洞区, 消除指甲的紫色拖影。
    keep_from_x: 该列以右保持原像素(腕部与袖子接壤处, 保证旋转时无缝)。"""
    h, w = hole.shape
    bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
    filled = cv2.inpaint(bgr, hole, 4, cv2.INPAINT_TELEA)
    filled = cv2.medianBlur(filled, 7)

    # 洞周围一圈的平均色 = 该处真实材质色
    ring = cv2.dilate(hole, np.ones((13, 13), np.uint8)) - hole
    ring_px = filled[ring > 0]
    if len(ring_px):
        mean_bgr = ring_px.mean(0)
        g = cv2.cvtColor(filled, cv2.COLOR_BGR2GRAY)
        mean_g = float(cv2.cvtColor(mean_bgr.reshape(1, 1, 3).astype(np.uint8),
                                     cv2.COLOR_BGR2GRAY)[0, 0])
        forced = np.clip(g[..., None].astype(np.float32) - mean_g + mean_bgr, 0, 255)
        a = cv2.GaussianBlur(hole, (0, 0), 2.0)[..., None].astype(np.float32) / 255.0
        filled = filled.astype(np.float32) * (1 - a) + forced * a
        filled = filled.astype(np.uint8)

    out = crop_rgb.copy()
    a = cv2.GaussianBlur(hole, (0, 0), 1.0)[..., None].astype(np.float32) / 255.0
    out = (filled.astype(np.float32) * a + crop_rgb.astype(np.float32) * (1 - a)).astype(np.uint8)
    local_x = keep_from_x - BOX[0]
    if 0 < local_x < w:
        out[:, local_x:] = crop_rgb[:, local_x:]
    return out


def main():
    sprite = np.array(Image.open(SPRITE).convert("RGBA"))
    H, W = sprite.shape[:2]
    x0, y0, x1, y1 = BOX
    crop = sprite[y0:y1, x0:x1, :3]

    m = hand_mask(crop)
    ch, cw = m.shape
    ys, xs = np.nonzero(m)
    print("hand bbox: x %d-%d  y %d-%d  (%d px)" %
          (xs.min() + x0, xs.max() + x0, ys.min() + y0, ys.max() + y0, (m > 0).sum()))

    # 腕部渐变, 让手层在袖口处自然融掉
    gx = np.arange(cw)[None, :] + x0
    ramp = np.clip((FADE_X1 - gx) / float(FADE_X1 - FADE_X0), 0, 1).astype(np.float32)
    alpha = (m.astype(np.float32) / 255.0) * ramp

    hand_alpha = np.zeros((H, W), np.uint8)
    hand_alpha[y0:y1, x0:x1] = (alpha * 255).astype(np.uint8)
    Image.fromarray(np.dstack([sprite[..., :3], hand_alpha]), "RGBA").save("assets/hand.png")

    hole = cv2.dilate(m, np.ones((9, 9), np.uint8))
    base_rgb = fill_hole(crop, hole, keep_from_x=478)
    base = sprite.copy()
    base[y0:y1, x0:x1, :3] = base_rgb
    Image.fromarray(base, "RGBA").save("assets/base.png")

    # ---- 审核: 绕腕旋转 0 / 2 / 4 度, 深色背景对比 ----
    hw = alpha                                   # 裁剪区内的 alpha, 不是全画布
    pivot = (PIVOT[0] - x0, PIVOT[1] - y0)
    rows = []
    for ang in (0.0, 2.0, 4.0):
        Mr = cv2.getRotationMatrix2D(pivot, -ang, 1.0)
        rot_rgb = cv2.warpAffine(crop, Mr, (cw, ch), flags=cv2.INTER_LANCZOS4,
                                 borderMode=cv2.BORDER_REPLICATE)
        rot_a = cv2.warpAffine(hw, Mr, (cw, ch), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
        dst = base_rgb.astype(np.float32).copy()
        a3 = rot_a[..., None]
        rows.append((rot_rgb.astype(np.float32) * a3 + dst * (1 - a3)).astype(np.uint8))
    Image.fromarray(np.hstack(rows)).resize((int(cw * 3 * 1.4), int(ch * 1.4)),
                                            Image.LANCZOS).save("build/review_rotate.png")
    print("hand.png / base.png ok  ->  build/review_rotate.png")


if __name__ == "__main__":
    main()
