# 美术资源需求文档（给 image2 用）

> 版本：2026-06-23
> 用途：列出当前工具需要的美术资源，附 image2 可直接使用的提示词。风格参考来自 Raycast.com / ElevenLabs.io / Linear.app（已用 Chrome 实地查看截图）。

---

## 一、风格方向

**基调**：深色科技感主底 + 暖色渐变光斑点缀 + 保留猪猪 IP 作为品牌锚点。

参考点：
- **Raycast.com**：纯黑背景、胶囊形导航/按钮、红色作为唯一强调色、极简无装饰。
- **ElevenLabs.io**：浅色主站背景里嵌入「柔和渐变圆形光斑」（紫→粉、橙→绿），用来表达"声音/AI 正在工作"，质感像磨砂玻璃上的光晕，不是扁平色块。
- **Linear.app**：深黑背景 + 大字重标题 + 极窄描边，干净但不冷。

**落到本工具**：
- 药丸（pill）本身已经是深色胶囊（`#101827`），现在加了渐变进度填充（蓝 `#1d4ed8` → 青 `#22d3ee`）——这个方向是对的，继续往「柔和光晕」而不是「死板色块」去做。
- 现有品牌 IP 是一只举着麦克风、说"AI处理"的猪猪（`icon.png`），偏可爱风格，和上面三家的"高级冷感"反差较大。**不建议丢掉猪猪**——它是当前唯一的品牌记忆点；建议保留猪猪用在「应用图标」「托盘图标」「空状态插画」上，但把「药丸」「设置界面背景」「统计看板」这些更高频出现的界面元素做成上面参考站的高级感风格，两者通过统一的色板（见下）连起来，不会显得割裂。

## 二、色板

| 用途 | 颜色 | 说明 |
|------|------|------|
| 药丸背景 | `#101827` | 已使用，深蓝黑 |
| 进度渐变起色 | `#1d4ed8` | 蓝，已使用 |
| 进度渐变终色 | `#22d3ee` | 青，已使用 |
| 强调色（错误/超时） | `#ef4444` → `#f59e0b` | 新增，用于"超时/失败"状态的药丸渐变，区别于正常处理 |
| 成功/完成 | `#22c55e` | 新增，替换成功一瞬的短暂高亮可用 |
| 猪猪 IP 背景渐变 | `#3b82f6 → #1e40af`（现有图标的蓝色系） | 保持现状 |

## 三、资源清单 + image2 提示词

> 每条资源给出：用途 / 尺寸建议 / 提示词。提示词用英文写（生成模型对英文 prompt 理解更准确），中文标注用途方便你对照。

### 3.1 药丸状态背景（4 态，可让 image2 一次性批量出）

**用途**：药丸 PillContainer 的背景纹理参考（当前是纯色+渐变代码绘制，如果想换成真实素材合成，可以用这组图当材质）。
**尺寸**：320×64px，圆角胶囊（border-radius = height/2），透明背景 PNG。

```
A horizontal pill-shaped UI capsule, fully rounded ends, dark navy-black background (#101827),
soft inner glow, frosted-glass texture, minimal, no text, no icons, transparent PNG background,
aspect ratio 5:1, app UI asset style like Raycast / Linear, subtle grain noise, 4K
```

四个变体（同一基础 prompt 加状态后缀）：
1. **录音中**：`+ a single soft cyan-blue glowing dot pulsing at the left edge, like a recording indicator`
2. **处理中**：`+ a horizontal gradient fill from blue (#1d4ed8) to cyan (#22d3ee) covering 60% of the width from the left, soft glow at the gradient edge`
3. **超时/失败**：`+ a horizontal gradient fill from red (#ef4444) to amber (#f59e0b), subtle warning glow`
4. **完成一瞬**：`+ a brief bright green (#22c55e) glow sweeping across the full pill from left to right`

### 3.2 应用图标 / 托盘图标变体

**用途**：当前 `icon.png` 是单一静态图标。建议补充「模型加载中」「就绪」「错误」三种托盘图标状态（Windows 系统托盘支持动态换图标）。
**尺寸**：256×256px，PNG，透明背景。

基础保留猪猪 IP，prompt：

```
Cute cartoon pig mascot character, friendly rounded design, holding a microphone,
[STATE_DETAIL], flat illustration with soft cel-shading, vibrant blue gradient background
(#3b82f6 to #1e40af), rounded square app icon frame, centered composition, clean vector style,
suitable for a Windows system tray icon, 256x256, transparent corners
```

- 就绪（绿色提示角标）：`STATE_DETAIL = "winking happily, small green dot badge on top-right corner indicating ready status"`
- 加载中（橙色提示角标 + 转圈）：`STATE_DETAIL = "looking focused with a small circular loading spinner badge on top-right corner, amber color"`
- 错误（红色提示角标）：`STATE_DETAIL = "looking concerned, small red exclamation badge on top-right corner"`

### 3.3 设置界面 Tab 图标（3 个，配合新的 Tab 布局）

**用途**：`通用` / `快捷键` / `行业词库` 三个 Tab，目前只有文字没有图标，加图标更易扫视。
**尺寸**：32×32px，单色线性图标（方便代码里用 QSS 染色，不要素材自带颜色）。

```
Minimal line icon, [ICON_SUBJECT], 2px stroke weight, rounded line caps, no fill,
monochrome black on transparent background, 32x32, flat vector icon style like
Linear.app's product icons, centered, plenty of padding
```

- 通用：`ICON_SUBJECT = "a simple gear/settings cog"`
- 快捷键：`ICON_SUBJECT = "a keyboard key outline with a small spark symbol on top"`
- 行业词库：`ICON_SUBJECT = "an open book with a small bookmark ribbon"`

### 3.4 使用统计看板（F6，配合需求文档 10.6 节的设计）

**用途**：独立窗口的统计看板背景 + 三个数据卡片底纹 + 热力图配色。
**尺寸**：卡片底纹 400×200px；看板背景 1200×800px。

看板整体背景：

```
Abstract dark dashboard background, deep navy-black (#0b0f1a), subtle soft blurred gradient
orbs in blue and cyan floating in the corners (like ElevenLabs.io's gradient orb style),
very subtle grid texture, minimal, lots of empty space for UI overlay, no text, 1200x800, 4K
```

三个成就卡片（次数 / 省时 / 连续天数）底纹，统一基础 + 不同强调色：

```
Rounded rectangle card background, dark glass morphism effect, soft border glow in
[ACCENT_COLOR], subtle inner gradient, minimal, no text, no icons, 400x200, transparent corners,
app dashboard card style like Linear.app
```

- 使用次数卡：`ACCENT_COLOR = "cyan (#22d3ee)"`
- 省时卡：`ACCENT_COLOR = "green (#22c55e)"`
- 连续打卡卡：`ACCENT_COLOR = "amber (#f59e0b)"`

热力图配色建议（不需要生成图片，直接给前端实现颜色梯度）：从 `#101827`（0 次）线性过渡到 `#22d3ee`（当日最高次数）。

### 3.5 空状态插画（首次使用引导、统计看板无数据时）

**用途**：统计看板首次打开、还没有任何使用记录时的占位插画。
**尺寸**：480×360px，透明背景。

```
Cute cartoon pig mascot (same character as the app icon) sitting and looking at an empty
chart/graph with a curious expression, minimal flat illustration, soft pastel accent colors
on a dark navy background (#101827), plenty of empty space around the subject, friendly and
approachable mood, no text, 480x360, transparent background
```

## 四、image2 批量生成 UI 控件的用法说明

你提到 image2 现在支持"一次性把 UI 控件全部生成并且切图"——这正好适合 3.1（药丸 4 态）和 3.3（Tab 图标 3 个）这两组，因为它们是同一基础风格的变体集合。建议：

1. 把同一组的 base prompt（如 3.1 的胶囊基础描述）和各状态的后缀分开输入，让 image2 在同一张画布里按网格排布全部变体，出图后用它的切图功能一次性导出。
2. 出图后检查圆角胶囊的边缘是否干净（深色背景出图常见的"边缘锯齿/光晕溢出"问题），如果不干净，让我后续用代码（QPainterPath 圆角裁剪，类似现在 `PillContainer.paintEvent` 已经做的）兜底裁剪，不依赖素材本身的边缘质量。
3. 所有素材统一使用透明背景 PNG，颜色尽量素材内嵌（药丸渐变可以直接用图，不用 QSS 再染色）；图标类（3.2/3.3）建议单色线性，方便代码里按需要染色复用。

## 五、不需要生成的部分

- 当前药丸的渐变进度填充已经用代码（`QLinearGradient` + `QPainterPath`）实现，效果可用，**不是必须替换成图片素材**——3.1 给的是"如果想要更精致的磨砂质感"的备选方案，不是阻塞项。
- 设置对话框的功能性控件（按钮、下拉框、输入框）用 Qt 原生样式即可，不需要定制素材，保持和 Windows 系统的一致性，过度定制反而会显得违和。
