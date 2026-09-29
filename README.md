# Moon 桌宠（Bongo Cat 式打字反馈）

一张 OC 插画 → 桌面宠物：**你敲键盘，她的手就按在笔记本键盘上**（绕腕关节下压 + 全身微微下沉），
空闲时会随机眨眼，鼠标点击会点头，鼠标穿透/拖动/托盘菜单齐全。

![预览](build/preview_sheet.png)

---

## 快速开始

```bat
pip install -r requirements.txt
run.bat                 :: 无控制台启动(推荐)
run_debug.bat           :: 带控制台启动, 排错用
python pet\main.py --demo   :: 演示模式, 自动模拟打字(不用真的敲)
```

素材已在 `assets/` 里生成好，直接跑即可。要改图/换图再往下看「素材流水线」。

## 操作

| 操作 | 效果 |
|---|---|
| 拖动 | 左键拖到屏幕任意位置（位置会记住） |
| 右键 | 菜单：大小 / 始终置顶 / 鼠标穿透 / 回到右下角 / 退出 |
| 托盘图标 | 单击显示-隐藏，右键同菜单 |
| 全局鼠标点击 | 她轻微点头 |
| `Ctrl+Alt+P` | 鼠标穿透开关（穿透后可点到底下的窗口） |
| `Ctrl+Alt+H` | 显示 / 隐藏 |

配置存在根目录 `config.json`（位置、缩放、置顶）。

---

## 动作是怎么做出来的

原画里她的手**已经贴在键盘上**，所以没有按"抬起→砸下"的经典 Bongo Cat 做法，而是：

- **按键 = 绕腕关节旋转 2.8°**（`PIVOT = (470, 1030)` 手腕处），指尖位移约 10px，手腕不动
  → 不会在袖口处撕裂，也不需要"补洞"就能成立；
- 同时全身以底边为锚点纵向压缩 0.26% 做打击感；
- 按下快（`ATTACK=26`）、回弹慢（`RELEASE=13`），并保证极短促的敲击也有 85ms 的可见动作（`KEY_PULSE`）；
- 打字越快，"热度"越高，下压幅度越大（`heat`）；
- 眨眼是把眼皮补丁盖在眼睛上（45ms 闭合 / 40ms 保持 / 75ms 睁开），随机 2.6~6.5s 一次，打字越快眨得越频；
- 手部旋转是**预渲染**成 51 张缓存（−1.0°~+4.0°，步长 0.1°），运行时只做贴图，CPU 占用极低。

## 文件结构

```
art/base.jpg            原图(768x1123)
assets/sprite.png       抠好像的全图(角色+帽子羽毛+椅子+桌子+笔记本)
assets/hand.png         打字的手(腕部 alpha 渐隐, 便于旋转)
assets/base.png         手背后已补洞的版本(留给以后的"抬手"动作)
assets/lid.png          闭眼眼皮补丁
pet/main.py             桌宠主程序
tools/step1_matte.py    整图抠像
tools/step2_hand.py     切手 + 补洞
tools/step3_eye.py      眨眼层
tools/preview_gif.py    离线渲染动图预览(不开窗口也能看动作)
build/                  各类验收图(见下)
```

## 素材流水线

```bat
python tools\step1_matte.py     :: -> assets/sprite.png + build/review_matte.png
python tools\step2_hand.py      :: -> assets/hand.png / base.png + build/review_rotate.png
python tools\step3_eye.py       :: -> assets/lid.png + build/review_lid.png
python tools\preview_gif.py     :: -> build/preview.gif + build/preview_sheet.png
python pet\main.py --selftest build\selftest.png   :: 离屏渲染各状态
```

几个关键实现点（换图时照着改就行）：

1. **抠像**靠三层：手工多边形硬约束 + 亮墙硬种子 + GrabCut 吸附边缘。黑色西装配深色椅子
   根本分不开，所以**椅子当场景道具保留**，只抠掉左上/右上那片亮墙。
2. **帽子羽毛**一半是白色，和亮墙同色，GrabCut 无解 —— 单用「比局部背景暗 / 高饱和紫」
   找它的描边，取连通域后填内部孔洞，再用 `FEATHER_HULL` 限制作用范围。
3. **切手**用色差而不是颜色：皮肤偏暖（`R−B>8`）、笔记本机身偏冷（`R−B<−6`）、
   袖子/指甲是高饱和紫（`R−B<−20 & S>45`），据此播种 GrabCut，比盲猜稳得多。
4. 半透明边缘做了**去白边**（按背景色反解），所以放在深色壁纸上也没有白色描边。

### 换成你自己的图

改 `tools/step1_matte.py` 里的 `KEEP_POLY`（保留区域轮廓，顺时针）→ 跑 step1；
改 `tools/step2_hand.py` 里的 `BOX`（手部框）和 `PIVOT`（腕关节）→ 跑 step2；
改 `tools/step3_eye.py` 里的 `BOX` / `EYE_POLY` / `NEW_LASH` → 跑 step3。
每步都会往 `build/` 输出审核图，对照着调坐标即可。

## 调参速查（`pet/main.py` 顶部）

| 常量 | 默认 | 作用 |
|---|---|---|
| `PRESS_ANGLE` | 2.8 | 按键时手的旋转角（度），想更夸张就调大 |
| `ATTACK` / `RELEASE` | 26 / 13 | 下压 / 回弹速度，越大越干脆 |
| `KEY_PULSE` | 0.085 | 保证极快敲击也有可见动作的时间 |
| `BODY_SQUASH` | 0.0026 | 打击感（全身纵向压缩比例） |
| `BLINK_*` | 0.05/0.04/0.075 | 眨眼三段时间 |
| `ANG_MIN/ANG_STEP/ANG_N` | −1.0/0.1/51 | 手部旋转预渲染范围（要抬手动作用负角度） |

## 打包成 exe

`release\MoonPet.exe`（单文件，53 MB，绿色免安装，目标机器不需要 Python）。
双击即用；首次启动要解包到临时目录，约 3~6 秒才出现。

重新打包：

```bat
pip install pyinstaller
tools\build_exe.bat
```

脚本会先从 `assets/sprite.png` 生成 `pet.ico`，再调 PyInstaller。要点：
`--add-data` 和 `--icon` 的路径**必须写绝对路径**（配 `--specpath` 时相对路径会按 spec 所在目录解析），
程序里也做了兼容：打包后素材从 `sys._MEIPASS\assets` 读，`config.json` 写在 **exe 旁边**（可写）。

> `--onefile` 启动慢、且个别杀毒软件会误报；想要秒开可以改成 `--onedir`（产出一个文件夹，里面放快捷方式）。

## 验收图（`build/`）

| 文件 | 看什么 |
|---|---|
| `review_matte.png` | 抠像轮廓（棋盘底 + 红线） |
| `zoom_corner.png` | 帽子羽毛区域边界 |
| `review_rotate.png` | 手腕旋转 0°/2°/4° 的接缝 |
| `review_lid.png` | 睁眼 / 闭眼对比（放大 4 倍 + 实际尺寸各一版） |
| `preview.gif` | 打字动图 |
| `selftest.png` | 五个状态并排 |

## 已知限制

- **只有一个姿势**。抬手动作用的是补洞后的 `base.png`，指甲附近可能留下轻微模糊（默认按压动作
  永远只"多盖住"，不会露洞，所以看不出来）。
- **闭眼是程序合成的**，不是原画 —— 放大看睫毛线不如原画手绘自然，但桌宠默认 55% 缩放下约 35px 宽，够用。
- **瞳孔没有跟随鼠标**：这只眼睛大部分是虹膜、没多少眼白，移动虹膜看起来会像整只眼在飘，不值得做。
- 托腮那只手不动（动了容易穿帮）。
- 全屏游戏/反作弊程序可能会屏蔽 pynput 的全局钩子，此时按键没反应。

## 下一步可以做什么

1. **分指独立敲击**：把手层再拆成「手指群 / 手掌」，只让手指做局部网格形变，并让不同键位对应不同手指；
2. **HID 直读模式**：绕开全局钩子，`hid` 库直接读键盘原始报文，全屏游戏里也能触发（Bongo Cat Mver 同款思路）；
3. **打包**：`pyinstaller --noconsole --add-data "assets;assets" pet/main.py`，配 `--icon`；
4. **音效**：敲击时叠一个很轻的机械键盘声，音量跟随打字速度；
5. **彩蛋**：右下角那杯红酒 —— 连敲太久液面晃一下 / 她喝一口。
