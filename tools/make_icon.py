# -*- coding: utf-8 -*-
"""从 sprite.png 生成 exe 图标 pet.ico (多尺寸)。"""
from PIL import Image, ImageDraw

SRC = "assets/sprite.png"
OUT = "pet.ico"

im = Image.open(SRC).convert("RGBA")
head = im.crop((120, 20, 580, 480))            # 帽子+脸
size = 256
head = head.resize((size, size), Image.LANCZOS)

# 圆形深色底, 让图标在浅色/深色任务栏上都清楚
plate = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(plate)
d.ellipse((4, 4, size - 4, size - 4), fill=(32, 30, 40, 255))
d.ellipse((4, 4, size - 4, size - 4), outline=(150, 130, 200, 255), width=4)
icon = Image.alpha_composite(plate, head)

icon.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
icon.resize((128, 128), Image.LANCZOS).save("build/icon_preview.png")
print("pet.ico ok")
