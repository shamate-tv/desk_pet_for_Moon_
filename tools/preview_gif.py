# -*- coding: utf-8 -*-
"""用 PIL 离线渲染一段打字动图(不依赖 Qt), 用于预览/验收动作曲线。
输出: build/preview.gif
"""
import os
import numpy as np
from PIL import Image

ASSETS = "assets"
HAND_BOX = (170, 900, 512, 1105)
LID_BOX = (325, 335, 415, 396)
PIVOT = (470.0, 1030.0)
PRESS_ANGLE, ATTACK, RELEASE = 2.8, 26.0, 13.0
SCALE, DT, FRAMES = 0.5, 0.055, 26
BLINK_AT, BLINK_LEN = 17, 4


def load(name):
    return Image.open(os.path.join(ASSETS, name)).convert("RGBA")


def main():
    sprite, hand, lid = load("sprite.png"), load("hand.png"), load("lid.png")
    hb = hand.crop(HAND_BOX)
    lb = lid.crop(LID_BOX)
    w, h = sprite.size

    # 模拟一段打字: 每隔 3 帧敲一次
    angles, t = [], 0.0
    cur = 0.0
    key_until = 0.0
    for i in range(FRAMES):
        if i % 3 == 0:
            key_until = t + 0.085
        target = PRESS_ANGLE if t < key_until else 0.0
        rate = ATTACK if target > cur else RELEASE
        cur += (target - cur) * min(1.0, rate * DT)
        angles.append(cur)
        t += DT

    frames = []
    for i, ang in enumerate(angles):
        f = sprite.copy()
        pr = hb.rotate(-ang, resample=Image.BICUBIC, center=(PIVOT[0] - HAND_BOX[0],
                                                            PIVOT[1] - HAND_BOX[1]))
        f.alpha_composite(pr, HAND_BOX[:2])
        if BLINK_AT <= i < BLINK_AT + BLINK_LEN:
            k = (i - BLINK_AT) / (BLINK_LEN - 1.0)
            alpha = min(1.0, 3 * k, 3 * (1 - k) + 0.6)
            lay = lb.copy()
            lay.putalpha(lay.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, alpha)))))
            f.alpha_composite(lay, LID_BOX[:2])
        frames.append(f.resize((int(w * SCALE), int(h * SCALE)), Image.LANCZOS))

    os.makedirs("build", exist_ok=True)
    # 抽 6 帧拼静图(方便直接看动作)
    idx = [0, 3, 6, 9, 13, BLINK_AT]
    w2, h2 = frames[0].size
    sheet = Image.new("RGB", (w2 * 3 + 8, h2 * 2 + 4), (20, 20, 22))
    for k, i in enumerate(idx):
        flat = Image.alpha_composite(Image.new("RGBA", frames[i].size, (36, 38, 48, 255)),
                                     frames[i]).convert("RGB")
        sheet.paste(flat, ((k % 3) * (w2 + 4), (k // 3) * (h2 + 2)))
    sheet.save("build/preview_sheet.png")
    # 棋盘底 + 深色底各一版, 方便看边缘
    out = []
    for fr in frames:
        flat = Image.alpha_composite(Image.new("RGBA", fr.size, (36, 38, 48, 255)), fr).convert("RGB")
        out.append(flat.quantize(colors=128, method=Image.MEDIANCUT))
    out[0].save("build/preview.gif", save_all=True, append_images=out[1:],
                duration=int(DT * 1000), loop=0, disposal=2)
    print("build/preview.gif ok  %d 帧  角度范围 %.2f~%.2f°" % (len(out), min(angles), max(angles)))


if __name__ == "__main__":
    main()
