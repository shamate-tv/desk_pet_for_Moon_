# -*- coding: utf-8 -*-
"""Bongo Cat 版素材流水线 —— 从 art/BongoCatOC抠图.png 切出可动图层。

产出 (assets/):
  base.png         底图: 两只爪子已挖掉并补好(爪子背面)
  paw_l.png        左手套爪 (全画布 RGBA)
  paw_r.png        右手套爪
  eyes_closed.png  闭眼补丁(用原画的线宽画两条闭眼线)

关键决定: 爪子动画只做"向下砸"(0 -> +dive), 因为砸下去只会多盖住;
只有回弹瞬间会在爪子上缘露出 d 像素的一条, 那条位于平涂的头发/脸上, 补起来很自然。
反过来"抬起"会在爪子下缘露出键盘的按键细节, 补不出来 -> 所以不做抬爪。
"""
import os
import cv2
import numpy as np
from PIL import Image

SRC = "art/BongoCatOC抠图.png"
OUT = "assets"
REVIEW = "build"

PAW_BOX = {                      # 两只爪子的包围盒 (x0, y0, x1, y1)
    "l": (322, 636, 536, 796),
    "r": (876, 706, 1064, 848),
}
# 左爪的描边在原图里是断的(断口两侧都是纯白, 无视觉差异) —— 分割时补一条闭合线,
# 但最终图层仍按真实像素取, 所以不会画出一条原图没有的黑线。
SEAL = {"l": [], "r": []}

# 左爪的描边在原图里是断的(断口两侧都是纯白, 切哪儿都看不出来), 所以直接手描外轮廓。
# 右爪描边闭合, 用自动分割。
PAW_POLY = {"l": [(352, 662), (368, 645), (395, 636), (430, 634), (462, 640), (480, 650),
                  (500, 672), (508, 690), (510, 705), (505, 725), (492, 745), (470, 760),
                  (440, 771), (405, 775), (372, 768), (348, 753), (334, 732), (330, 708),
                  (338, 682), (345, 668)]}
FACE_BOX = (380, 360, 820, 580)  # 找眼睛用


def paw_masks(rgb, alpha):
    """爪子 = 被黑色描边闭合围住的白色区域, 再沿描边向外"吃到"描边外缘。"""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dark = ((gray < 80) & (alpha > 180)).astype(np.uint8)
    out = {}
    for name, (x0, y0, x1, y1) in PAW_BOX.items():
        if name in PAW_POLY:                       # 手描的优先
            full = np.zeros(alpha.shape, np.uint8)
            cv2.fillPoly(full, [np.array(PAW_POLY[name], np.int32)], 255)
            out[name] = cv2.bitwise_and(full, (alpha > 40).astype(np.uint8) * 255)
            continue
        sd = dark[y0:y1, x0:x1].copy()
        for (p1, p2) in SEAL.get(name, []):        # 只在分割掩膜上补口
            cv2.line(sd, (p1[0] - x0, p1[1] - y0), (p2[0] - x0, p2[1] - y0), 1, 9)
        pad = 2                                    # 补一圈"非黑"边框, 保证外部连通
        sdp = np.pad(sd, pad, constant_values=0)
        ff = (1 - sdp).astype(np.uint8)
        cv2.floodFill(ff, np.zeros((sdp.shape[0] + 2, sdp.shape[1] + 2), np.uint8),
                      (0, 0), 2)
        enclosed = (ff == 1)[pad:-pad, pad:-pad].astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(enclosed, 8)
        if n <= 1:
            raise SystemExit("没找到 %s 的爪心" % name)
        k = 1 + int(np.argmax(st[1:, 4]))           # 最大的封闭区 = 爪心
        interior = np.where(lab == k, 255, 0).astype(np.uint8)
        paw = interior.copy()                       # 只向黑色描边内部生长, 限 16 步
        for _ in range(16):
            grown = cv2.bitwise_and(cv2.dilate(paw, np.ones((3, 3), np.uint8)), sd * 255)
            new = cv2.bitwise_and(grown, cv2.bitwise_not(paw))
            if new.sum() == 0:
                break
            paw = cv2.bitwise_or(paw, new)
        full = np.zeros(alpha.shape, np.uint8)
        full[y0:y1, x0:x1] = paw
        out[name] = full
    return out


def fill_holes(img, masks):
    """补爪子背面。
    爪子周围全是交错的粗描边, inpaint/最近邻都会糊成灰带。这里按列处理:
    从爪子上缘往上"跳过描边", 取第一块平涂色(头发紫 / 脸白), 再往下抹一段。
    只有回弹露出的那几像素会被看到, 所以只抹 EXT 这么高。
    """
    hole = np.zeros(masks["l"].shape, np.uint8)
    for m in masks.values():
        hole = cv2.bitwise_or(hole, m)
    hole = cv2.dilate(hole, np.ones((3, 3), np.uint8))
    h, w = hole.shape
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    EXT = 16
    filled = img.copy()
    for x in range(w):
        ys = np.nonzero(hole[:, x])[0]
        if len(ys) == 0:
            continue
        y0, y1 = int(ys[0]), int(ys[-1])
        y = y0 - 1
        while y > max(0, y0 - 45) and gray[y, x] < 110:      # 跳过描边, 落到平涂区
            y -= 1
        k = min(EXT, y1 - y0 + 1)
        filled[y0:y0 + k, x] = img[y, x]
        if y1 - y0 + 1 > k:
            filled[y0 + k:y1 + 1, x] = img[min(h - 1, y1 + 1), x]
    a = cv2.GaussianBlur(hole, (0, 0), 1.2)[..., None].astype(np.float32) / 255.0
    return (filled.astype(np.float32) * a + img.astype(np.float32) * (1 - a)).astype(np.uint8)


def find_eyes(rgb, alpha):
    """脸部两个圆黑点就是眼睛。"""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dark = ((gray < 120) & (alpha > 180)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(dark, 8)
    eyes = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if not (800 < area < 5000):
            continue
        fill = area / float(w * h)
        ar = w / float(max(h, 1))
        if 0.68 < fill < 0.92 and 0.8 < ar < 1.25:      # 又圆又实心
            eyes.append((int(cen[i][0]), int(cen[i][1]), int(w), int(h)))
    eyes.sort()
    return eyes


def make_closed_eyes(rgb, alpha, eyes):
    """闭眼: 用脸的同色盖掉眼点, 再按同样的线宽画一条横线。"""
    closed = rgb.copy()
    a = np.zeros(alpha.shape, np.uint8)
    for (ex, ey, w, h) in eyes:
        rr = int(max(w, h) * 0.65)
        ring = np.zeros(alpha.shape, np.uint8)
        cv2.circle(ring, (ex, ey), int(rr * 2.1), 255, -1)
        cv2.circle(ring, (ex, ey), int(rr * 1.25), 0, -1)
        px = rgb[ring > 0]
        col = np.median(px, 0) if len(px) else np.array([255, 255, 255])
        cv2.circle(closed, (ex, ey), int(rr * 1.15), tuple(float(c) for c in col), -1)
        half = int(w * 0.60)
        th = max(7, int(h * 0.34))
        cv2.line(closed, (ex - half, ey), (ex + half, ey), (26, 22, 34), th, cv2.LINE_AA)
        cv2.circle(a, (ex, ey), int(rr * 1.6), 255, -1)
    a = cv2.GaussianBlur(a, (0, 0), 1.5)
    return closed, a


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REVIEW, exist_ok=True)
    im = np.array(Image.open(SRC).convert("RGBA"))
    rgb, alpha = im[..., :3], im[..., 3]

    masks = paw_masks(rgb, alpha)
    for k, v in masks.items():
        ys, xs = np.nonzero(v)
        print("paw_%s: %d px, bbox x %d-%d y %d-%d" %
              (k, len(ys), xs.min(), xs.max(), ys.min(), ys.max()))

    # 爪子层(带原 alpha)
    for name, m in masks.items():
        a = np.minimum(m, alpha)
        a = cv2.GaussianBlur(a, (0, 0), 1.0)
        full = np.dstack([rgb, a])
        Image.fromarray(full, "RGBA").save(os.path.join(OUT, "paw_%s.png" % name))

    # 底图(挖掉爪子再补)
    base_rgb = fill_holes(rgb, masks)
    Image.fromarray(np.dstack([base_rgb, alpha]), "RGBA").save(os.path.join(OUT, "base.png"))

    # 闭眼
    eyes = find_eyes(rgb, alpha)
    if len(eyes) < 2:
        raise SystemExit("只找到 %d 个眼睛, 检查 find_eyes 阈值" % len(eyes))
    print("眼睛:", eyes)
    closed, closed_alpha = make_closed_eyes(rgb, alpha, eyes)
    Image.fromarray(np.dstack([closed, closed_alpha]), "RGBA").save(
        os.path.join(OUT, "eyes_closed.png"))

    # ---- 审核图: 左=静止, 右=两爪各下砸 14px ----
    def comp(dy):
        canvas = Image.fromarray(np.dstack([base_rgb, alpha]))
        for name in masks:
            layer = Image.open(os.path.join(OUT, "paw_%s.png" % name)).convert("RGBA")
            canvas.alpha_composite(layer, (0, int(dy)))
        return np.array(canvas)

    tiles = []
    for dy in (0, 14):
        f = comp(dy)[560:900, 140:1330]
        bg = np.full(f.shape[:2] + (3,), 245, np.uint8)
        a3 = f[..., 3:4].astype(np.float32) / 255
        tiles.append((f[..., :3] * a3 + bg * (1 - a3)).astype(np.uint8))
    Image.fromarray(np.hstack(tiles)).save(os.path.join(REVIEW, "review_bongo.png"))

    # 睁眼/闭眼对比
    eye_box = (470, 470, 950, 680)
    open_face = rgb[eye_box[1]:eye_box[3], eye_box[0]:eye_box[2]]
    closed_face = closed[eye_box[1]:eye_box[3], eye_box[0]:eye_box[2]]
    Image.fromarray(np.hstack([open_face, np.full((closed_face.shape[0], 8, 3), 255, np.uint8),
                               closed_face])).save(os.path.join(REVIEW, "review_bongo_eyes.png"))
    print("assets_bongo/: base.png paw_l.png paw_r.png eyes_closed.png")
    print("审核图: build/review_bongo.png  build/review_bongo_eyes.png")


if __name__ == "__main__":
    main()
