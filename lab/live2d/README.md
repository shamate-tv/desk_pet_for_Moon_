# lab / live2d —— 实验记录（已结案：不做）

2026-10-01 做的一轮 Live2D 可行性验证。**结论：技术上完全可行，但美术成本太高，项目决定不采用。**
这里留下代码和数据，以后想重开不用从零开始。

## 验证结果（都是实测）

| 检查项 | 结果 |
|---|---|
| 库 | `live2d-py 1.0.0`（`cp311-abi3` wheel，Python 3.14 可直接装），内部是 Cubism SDK **5-r.5** |
| 模型 | 官方示例 Haru（`.moc3` + 25 动作 + 物理 + 表情）加载正常，含 `v2/framework`（动作混合/物理/自动眨眼呼吸/姿势/点击命中） |
| 渲染 | Qt **离屏 GL 上下文 + 自建 FBO** → `glReadPixels` → numpy → QImage |
| 接入现有壳 | ✅ 透明窗口 / 置顶 / 拖拽 / 托盘 / 全局键鼠钩子 **一行没改**，只把"贴 PNG"换成"贴 GL 帧" |
| 打字响应 | `StartMotion("TapBody")` |
| 跟随鼠标 | `ParamAngleX/Y/Z` + `ParamEyeBallX/Y` + `ParamBodyAngleX` |
| 性能 | 600×900 含读回 **1.80 ms/帧**（p95 2.33）；420×630 只要 1.35 ms |
| 打包 | PyInstaller 单文件 exe（67MB，含 4.2MB 模型）实测能跑 |

## 两个踩过的坑（重要）

1. **必须自己建 FBO**。Qt 的 `QOffscreenSurface` 默认帧缓冲**读不回来**——
   第一次测的时候清成纯红，`glReadPixels` 照样返回全 0，害我以为是 Live2D 没画出来。绑定自建 FBO 后一切正常。
2. **打包要带两样东西**：
   ```bat
   --collect-data live2d --hidden-import live2d._live2d
   ```
   缺 `FrameworkShaders`（GLSL 着色器，运行时从包目录读）就白屏。

## 为什么最后没做

`.moc3` **只能由 Live2D Cubism Editor 从分层 PSD 绑定生成**——AI 生不出来，代码也写不出来。
而我们的美术来源是 AI + 手工分层，团队里没人会画画。要做 Moon 的模型，得先产出
"胸像级 8~12 层、且被遮挡部分都补画好"的 PSD，再有人花 1~3 天学 Cubism Editor 做绑定。

对"打字拍桌子的桌宠"来说，这个投入产出比不划算：她大半身子被桌子挡着，
Live2D 最贵的身体/大幅动作能力基本浪费；而现在的分层 PNG + 弹簧动画已经够用。

**重新评估这条路的前提是**：① 有人愿意学绑定 ② 想复用模型到别处（VTube Studio 等）
③ 打算持续加很多新动作（那时"调参数"比"每次重画"划算）。

另外别忘了授权：公开分发带 Cubism Core 的程序要遵守[商标展示指南](https://www.live2d.com/zh-CHS/sdk/guidelines/)，
可能还要签出版许可。

## 文件

| 文件 | 说明 |
|---|---|
| `live2d_pet.py` | 集成 demo：桌宠壳 + Live2D 渲染 + 跟随鼠标（把 `models/Haru` 放回来就能跑） |
| `l2d_fbo.py` | 最小验证：FBO + 渲染 + 读回存图 |
| `l2d_perf.py` | 帧耗时基准 |
| `dl_sample.py` | 从官方仓库下示例模型 Haru |

重开的话：
```bat
py -3.14 -m pip install live2d-py
python lab\live2d\dl_sample.py          :: 下模型到 build/live2d_sample
python lab\live2d\l2d_fbo.py            :: 验证渲染
python lab\live2d\live2d_pet.py         :: 跑桌宠 demo（需要 models/Haru）
```


---

# BongoCat (vladelaina/BongoCat) 模型适配规则

2026-10-01 实测摸清。**以后给这个应用做模型，照这份走即可。**

## 1. 模型放哪、怎么被认出来

```
%LOCALAPPDATA%\BongoCat\models\<名字>\     ← 不是安装目录(安装目录的 assets/models 是空的)
    .bongo-cat-builtin      必须有！否则扫描时整个目录被跳过（源码 model_catalog.c）
    .bongo-cat-mode         内容写 standard / keyboard / gamepad
    cat.model3.json         文件名必须叫这个
    *.moc3  texture_00.png  ...
    resources/              见第 4 节
```
模式判定顺序：`.bongo-cat-mode` 内容 → 目录名 → 有没有 `resources/right-keys/`（有=键盘，没有=Standard）

## 2. 各模式驱动哪些手部参数（从官方三个模型 + app_state.c 反推）

| 模式 | 打字/输入驱动的手部参数 |
|---|---|
| keyboard | `CatParamLeftHandDown` / `CatParamRightHandDown` |
| standard | `Param` / `Param2`（它的动作文件动的就是这两个）|
| gamepad  | `CatParamStickLeftDown` / `CatParamStickRightDown` + `CatParamStickShowLeft/RightHand` |

鼠标：`ParamMouseX/Y`、`ParamMouseLeftDown/RightDown`。
**手部参数按模式分开出变体**，别指望一套参数通吃三个模式。

## 3. 拍手靠"播放动作"，不是直接推参数

`app_state.c` 的真实链路：

```
敲键 -> apply_key() -> bongo_cat_overlay_key(overlay, 键名, pressed)
                    -> 返回 <0 直接 return（键不在映射表里就什么都不发生）
                    -> update_hands() 才设置 CatParamLeft/RightHandDown
```
- 键位映射表 = **模型目录里的 `resources/left-keys/*.png` + `resources/right-keys/*.png`**（文件名就是键名）
- 模型还必须自带 `Motions`（官方用组名 `CAT_motion` / `CAT_motion_lock`），应用按组播放
- **模型没有 `resources/` 或没有动作文件 → 在应用里永远不动**（我们在这上面卡了很久）

## 4. overlay 与画布几何

```
应用分层:  resources/background.png(桌面/键盘) -> [模型] -> resources/cover.png(桌沿前景)
           + left-keys/right-keys(键帽高亮, 按下会亮)
```
- **模型里只放角色**，桌面/键盘/键帽都交给 overlay（官方模型的 bg 也只有猫本体）
- 画布几何必须和官方一致才能对齐：**612×354 / origin 居中 / ppu 354**
- overlay 的**所有图都是"全画布尺寸"**（612×354），不是小图标

## 5. 调位置的两个手段（重要）

| 手段 | 改什么 | 副作用 |
|---|---|---|
| ① 改模型坐标 | `ART_OFF_X/Y` | 会同时改变"头顶空间"和"桌沿对齐"；超出余量就切头/悬空 |
| ② 给 overlay 图补顶 | 每张图顶部加 N 行透明 + 画布高度 +N | **永不破坏对齐**，桌沿跟着走 |

几何约束：`头顶到桌沿 = 657 × 缩放`（本例），而 overlay 桌沿在画布里的高度决定可用空间：
**桌沿画布 y ≥ 657 × 缩放**，头顶才不会被切。想放大又要头顶完整，就只能用手段 ②。

## 6. 隐藏部件用"透明度"，不要删 drawable

把 drawable 从模型里删掉会让 moc3 结构失效 → **官方 Core 直接崩**（进程无输出退出）。
正确做法：保留 drawable，把它的关键形透明度 `art_mesh_keyform.opacities` 设 0。

## 7. 其他坑

- `Update()` 每帧会重置参数 → 必须 `Update()` → `SetParamById()` → `Draw()`
- 关键形位置块要**逐片**补到 16 float 对齐；补在数组末尾会让第 2 片起整体错位
- `keyform_begin_indices` 是**关键形序号**（当偏移解释会导致 Core 拒载）
- 打包/发布前用官方 Core 实测加载：`live2d.Model().LoadModelJson(...)`
