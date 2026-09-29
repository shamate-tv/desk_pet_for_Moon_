# -*- coding: utf-8 -*-
"""Bongo 版离线动图预览(不依赖 Qt)。输出 build/preview_bongo.gif + 分帧图。"""
import os
import math
import numpy as np
from PIL import Image

ASSETS = "assets"
PAW_BOX = {"l": (318, 620, 525, 800), "r": (864, 708, 1048, 856)}
EYE_BOX = (494, 490, 920, 680)
LIFT_PX, PAW_SQUASH, PAW_WIDEN = 30.0, 0.16, 0.08
HOVER_K, HOVER_C = 150.0, 17.0
BODY_SQUASH, BODY_WIDEN = 0.020, 0.006
K_HIT, C_HIT, IMPULSE = 900.0, 40.0, 9.0
K_BODY, C_BODY, IMP_BODY = 620.0, 34.0, 4.9
SCALE, DT, FRAMES = 0.46, 1 / 60.0, 78
BLINK_AT, BLINK_LEN = 62, 8


def main():
    base = Image.open(os.path.join(ASSETS, "base.png")).convert("RGBA")
    eyes = Image.open(os.path.join(ASSETS, "eyes_closed.png")).convert("RGBA").crop(EYE_BOX)
    paws = {k: Image.open(os.path.join(ASSETS, "paw_%s.png" % k)).convert("RGBA").crop(PAW_BOX[k])
            for k in ("l", "r")}
    W, H = base.size

    pv = {"l": 0.0, "r": 0.0}
    pw = {"l": 0.0, "r": 0.0}
    up = {"l": 0.0, "r": 0.0}
    upv = {"l": 0.0, "r": 0.0}
    off = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
    offv = {"l": [0.0, 0.0], "r": [0.0, 0.0]}
    body = bv = 0.0
    cur, nxt = "l", "r"
    frames = []
    for i in range(FRAMES):
        if i % 7 == 0:                                  # 每 7 帧敲一次, 左右交替
            pw[cur] += IMPULSE
            upv[cur] -= 13.0                            # 砸下去: 抬爪量压到 0
            bv += IMP_BODY
            rk = (i // 7) % 6                           # 右爪去按不同的键
            off["r"] = [(-120.0 + 150.0 * rk) * 0.9, (-40.0 + 62.0 * rk)]
            cur, nxt = nxt, cur
        typing = (i % 60) < 52
        for k in ("l", "r"):
            pw[k] += (-K_HIT * pv[k] - C_HIT * pw[k]) * DT
            pv[k] = min(1.35, max(0.0, pv[k] + pw[k] * DT))
            goal = 1.0 if typing else 0.0
            upv[k] += (-HOVER_K * (up[k] - goal) - HOVER_C * upv[k]) * DT
            up[k] = min(1.25, max(0.0, up[k] + upv[k] * DT))
        mouse = [-150.0 + 150.0 * math.sin(i * DT * 0.9), 22.0 * math.sin(i * DT * 0.6)]
        for k in ("l", "r"):
            for j in (0, 1):
                tgt = (mouse[j] if k == "l" else off["r"][j])
                offv[k][j] += (70.0 * (tgt - off[k][j]) - 13.0 * offv[k][j]) * DT
                off[k][j] += offv[k][j] * DT
        bv += (-K_BODY * body - C_BODY * bv) * DT
        body = min(1.35, max(0.0, body + bv * DT))

        sy, sx = 1 - BODY_SQUASH * body, 1 + BODY_WIDEN * body
        nw, nh = int(W * sx), int(H * sy)
        f = base.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (nw, H), (0, 0, 0, 0))
        canvas.alpha_composite(f, (int((nw - nw) / 2), H - nh))
        for k in ("l", "r"):
            v = pv[k]
            if v <= 0.002 and up[k] <= 0.002 and abs(off[k][0]) < 1 and abs(off[k][1]) < 1:
                canvas.alpha_composite(paws[k], PAW_BOX[k][:2])
                continue
            b = paws[k]
            b = b.resize((max(1, int(b.width * (1 + PAW_WIDEN * v))),
                          max(1, int(b.height * (1 - PAW_SQUASH * v)))), Image.BICUBIC)
            canvas.alpha_composite(b, (int(PAW_BOX[k][0] + off[k][0]),
                                       int(PAW_BOX[k][1] + off[k][1] - LIFT_PX * up[k])))
        if BLINK_AT <= i < BLINK_AT + BLINK_LEN:
            k = (i - BLINK_AT) / (BLINK_LEN - 1.0)
            a = min(1.0, 3 * k, 3 * (1 - k) + 0.6)
            e = eyes.copy()
            e.putalpha(e.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, a)))))
            canvas.alpha_composite(e, EYE_BOX[:2])
        frames.append(canvas.resize((int(nw * SCALE), int(H * SCALE)), Image.LANCZOS))

    os.makedirs("build", exist_ok=True)
    out = []
    for fr in frames:
        flat = Image.alpha_composite(Image.new("RGBA", fr.size, (36, 38, 48, 255)), fr).convert("RGB")
        out.append(flat.quantize(colors=64, method=Image.MEDIANCUT))
    out[0].save("build/preview_bongo.gif", save_all=True, append_images=out[1:],
                duration=int(DT * 1000), loop=0, disposal=2)

    idx = [0, 8, 15, 30, 45, BLINK_AT + 3]
    w2, h2 = frames[0].size
    sheet = Image.new("RGB", (w2 * 3 + 8, h2 * 2 + 4), (20, 20, 22))
    for n, i in enumerate(idx):
        flat = Image.alpha_composite(Image.new("RGBA", frames[i].size, (36, 38, 48, 255)),
                                     frames[i]).convert("RGB")
        sheet.paste(flat, ((n % 3) * (w2 + 4), (n // 3) * (h2 + 2)))
    sheet.save("build/preview_bongo_sheet.png")
    print("build/preview_bongo.gif  %d 帧  %s" % (len(out), frames[0].size))


if __name__ == "__main__":
    main()
