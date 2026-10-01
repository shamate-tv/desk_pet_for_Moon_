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
