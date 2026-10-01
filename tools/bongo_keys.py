# -*- coding: utf-8 -*-
"""生成 skins/moon/keys.json —— 每个键帽在底图上的中心坐标。

做法:
  1. 在干净的键盘层上自适应阈值 + 轮廓筛选, 找出若干键帽中心;
  2. 用键帽中心反推键盘的网格基向量(行向 R / 列向 V), 得到每个键帽的整数格坐标 (i, j);
  3. 用这些 (i,j) -> 图像坐标 的对应点拟合单应矩阵(键盘有透视, 等距格子到边缘会漂);
  4. 按标准键盘布局把 (行,列) 映射到格坐标, 再用单应矩阵算出图上位置。

注意: 键盘是**正常布局**(1-0 / QWERTY / ASDF / ZXCV, 左 Tab/Caps/Shift, 右 Enter),
      但在画面里是**倒过来的(旋转 180°)** —— 字母本身是正的, 可键位排布是反的。
      所以两个轴都要翻转:
          std_row = R0 - j,  std_col = C0 - i      (锚点 (i,j)=(0,0) 是 "G" = (行2, 列4))
"""
import cv2
import json
import numpy as np
import os
from PIL import Image

KB = "art/键盘.png"
OUT = "skins/moon/keys.json"
REF = "art/BongoCatOC抠图.png"
P0 = np.array([879.0, 880.0])        # 锚点: "H" 键中心
R = np.array([49.5, 10.5])           # +i: 键盘上向右一个键
V = np.array([-9.0, 45.0])           # +j: 键盘上向下一行
H0 = (2, 4)                          # 锚点(879,880) 是 "G" 键, 标准布局 (行2, 列4)
# 整体微调(按用户实测, 两轮累加):
#   第一轮: 右移 2 键(+2R) + 下移 1 键(+V)            -> (90, 66)
#   第二轮: 左移 1 键(-R)   + 上移半键(-0.5V)          -> (-45, -33)
#   合计   -> (45, 33)
# 以后再偏只改这一个数:  右1键=(49.5,10.5) 左1键=(-49.5,-10.5)
#                       下1行=(-9,45)     上1行=(9,-45)  半个键就取一半
SHIFT = (45.0, 33.0)
LAYOUT = ["`1234567890-=", "\tqwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"]


def detect_keys():
    kb = np.array(Image.open(KB).convert("RGBA"))
    g = cv2.GaussianBlur(cv2.cvtColor(kb[..., :3], cv2.COLOR_RGB2GRAY), (3, 3), 0)
    ad = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 41, -6)
    ad[kb[..., 3] < 150] = 0
    ad = cv2.morphologyEx(ad, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(ad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)
        if 700 < area < 12000 and 35 < w < 170 and 22 < h < 110 and area / (w * h) > 0.55:
            M = cv2.moments(c)
            out.append([M["m10"] / M["m00"], M["m01"] / M["m00"]])
    return np.array(out, float)


def main():
    det = detect_keys()
    Minv = np.linalg.inv(np.array([R, V]).T)
    src, dst = [], []
    for p in det:
        ij = Minv @ (p - P0)
        ijr = np.round(ij)
        if np.abs(ij - ijr).max() <= 0.25:          # 只留落在格点上的
            src.append(ijr)
            dst.append(p)
    src = np.array(src, np.float32).reshape(-1, 1, 2)
    dst = np.array(dst, np.float32).reshape(-1, 1, 2)
    H, _ = cv2.findHomography(src, dst, 0)
    pred = cv2.perspectiveTransform(src, H)
    err = np.linalg.norm(pred - dst, axis=2).ravel()

    keys = {}
    def put(name, std_row, std_col):
        ij = np.array([[[H0[1] - std_col, H0[0] - std_row]]], np.float32)   # 键盘倒置 => 两轴翻转
        p = cv2.perspectiveTransform(ij, H)[0][0]
        keys[name] = [round(float(p[0]) + SHIFT[0], 1), round(float(p[1]) + SHIFT[1], 1)]

    for r, row in enumerate(LAYOUT):
        for c, ch in enumerate(row):
            put(ch, r, c)
    put("esc", -1, 0)
    put(" ", 4, 5)
    json.dump(keys, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("用 %d 个键帽拟合, 残差 平均%.1fpx 最大%.1fpx -> %s (%d 个键位)"
          % (len(src), err.mean(), err.max(), OUT, len(keys)))

    im = Image.open(REF).convert("RGBA")
    bg = Image.new("RGBA", im.size, (245, 245, 248, 255))
    bg.alpha_composite(im)
    v = np.array(bg.convert("RGB"))
    for ch, (x, y) in keys.items():
        cv2.circle(v, (int(x), int(y)), 6, (255, 0, 0), 2)
    os.makedirs("build", exist_ok=True)
    Image.fromarray(v[700:1078, 450:1400]).resize((902, 359), Image.LANCZOS).save(
        "build/keymap_check.png")
    print("审核图 -> build/keymap_check.png")


if __name__ == "__main__":
    main()
