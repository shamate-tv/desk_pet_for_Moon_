# -*- coding: utf-8 -*-
"""从 pet/main.py 里的 VERSION 生成 PyInstaller 的 Windows 版本资源。
输出: build/version_info.txt (给 --version-file 用)
      build/ver.txt          (给 build_exe.bat 读, 用于命名 exe)
改版本号只需要改 pet/main.py 顶部的 VERSION 一处。
"""
import os
import re

SRC = os.path.join("pet", "main.py")
OUT_DIR = "build"

ver = None
for line in open(SRC, encoding="utf-8"):
    if line.startswith("VERSION"):
        ver = line.split('"')[1]
        break
if not ver:
    raise SystemExit("在 pet/main.py 里找不到 VERSION")

parts = [int(x) for x in re.findall(r"\d+", ver)]
while len(parts) < 4:
    parts.append(0)
quad = ", ".join(str(p) for p in parts[:4])

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "ver.txt"), "w", encoding="utf-8") as fh:
    fh.write(ver)

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({quad}),
    prodvers=({quad}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', 'Moon'),
        StringStruct('FileDescription', 'Moon 桌宠 - Bongo Cat 式打字反馈'),
        StringStruct('FileVersion', '{ver}.0'),
        StringStruct('InternalName', 'MoonPet'),
        StringStruct('OriginalFilename', 'MoonPet-v{ver}.exe'),
        StringStruct('ProductName', 'Moon 桌宠'),
        StringStruct('ProductVersion', '{ver}'),
        StringStruct('Comments', 'OC: Moon / 素材由 tools/step*.py 从单张插画自动切分')])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
with open(os.path.join(OUT_DIR, "version_info.txt"), "w", encoding="utf-8") as fh:
    fh.write(TEMPLATE.format(quad=quad, ver=ver))
print("version_info.txt / ver.txt  -> %s" % ver)
