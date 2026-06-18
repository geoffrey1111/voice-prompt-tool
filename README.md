# Voice Prompt Tool

**说话，它来整理** — 在任意输入框按下快捷键，用声音代替打字。口语随便说，输出逻辑清晰的书面文字。

**Speak freely, get polished text** — press a hotkey in any text field, speak naturally, and get clean, structured written output powered by local AI. No cloud, no subscription.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## English

### What It Does

Voice Prompt Tool sits in your system tray and listens for a hotkey. Press it in any text field — WeChat, a browser, VS Code, Notepad — speak naturally, and it writes polished text directly into that field.

Two modes:

| Mode | Hotkey | What it does |
|------|--------|-------------|
| **AI mode** | `Ctrl + Space` | Transcribes your speech, then rewrites it into clear, logical written text using a local Qwen3 model |
| **Dictation mode** | `Right Alt` | Transcribes speech and appends it directly — no AI rewriting, faster |

### Why It's Different

- **Fully offline** — ASR and AI both run locally. No API keys, no accounts, no data leaving your machine.
- **Works in any input field** — injects text via Win32 API, so it works everywhere: chat apps, browsers, editors, terminals.
- **Live replacement** — in AI mode, the raw transcript appears first, then gets selected and replaced by the polished version. The transition is instant and satisfying.
- **Faster than cloud-based alternatives** — local inference is significantly faster than API round-trips.

### Perfect For

- **Vibe coding** — speak your requirements to Claude/GPT instead of typing. The AI mode structures your intent into a clean prompt automatically.
- **AI short-drama writers** — brainstorm plot ideas out loud; get structured scene notes.
- **Work communication** — ramble about a task, send a coherent message.
- **Quick note-taking** — capture ideas before they disappear.

### Supported Languages

| Language | ASR Model | Notes |
|----------|-----------|-------|
| 中文 (Chinese) | SenseVoice Small | Default, optimized for Mandarin |
| English | Whisper medium | Switch in Settings → Language |

Switch language in **tray → Settings → Language / 语言**. Switching to English downloads the Whisper medium model (~1.5 GB) on first use.

### Setup

**Requirements:** Windows 10 / 11 (64-bit)

```powershell
# First-time setup (downloads models, ~3 GB)
.\setup.ps1

# Launch
.\desktop.ps1
```

Or double-click `启动 Voice Prompt Tool.exe`.

### Models

| Component | Model | Purpose |
|-----------|-------|---------|
| ASR (Chinese) | SenseVoice Small | Speech-to-text |
| ASR (English) | Whisper medium | Speech-to-text |
| AI rewriting | Qwen3 (local via Ollama) | Rewrites spoken language into written text |

### Tech Stack

- **GUI**: PySide6 (Qt), frameless pill overlay
- **ASR**: FunASR / SenseVoice · faster-whisper
- **AI inference**: Ollama + Qwen3
- **Text injection**: Win32 API (SendMessage)
- **Global hotkeys**: WH_KEYBOARD_LL low-level keyboard hook

---

## 中文

### 功能特点

- **任意输入框可用** — 微信、浏览器、记事本、代码编辑器，按键即用
- **两种模式**：AI 润色模式 + 极速听写模式
- **完全本地运行** — 语音识别与 AI 均在本机执行，无需联网，数据不外传
- **后台常驻无感知** — 系统托盘驻留，不占前台窗口
- **支持中英文** — 中文用 SenseVoice，英文用 Whisper，设置中切换

### 两种使用模式

#### AI 模式（Ctrl + Space）

口语 → AI 整理 → 书面文字，自动写入当前输入框。

| 步骤 | 说明 |
|------|------|
| 1 | 光标定位到任意输入框，按 **Ctrl + Space** 开始录音 |
| 2 | 自然说话，屏幕底部出现悬浮状态条「AI模式（录音中）」 |
| 3 | 再按 **Ctrl + Space** 停止，ASR 转录结果先写入输入框 |
| 4 | AI 自动润色，将口语改写为逻辑清晰的书面表达 |
| 5 | 润色后的文字替换原转录内容，状态条消失 |

**示例：**

> 说：「就是那个需求啊，用户登录那块，感觉现在有点问题，每次都要重新输密码，很烦」
>
> 输出：「用户登录模块存在体验问题：每次会话结束后需重新输入密码，缺少登录态保持机制，建议增加"记住我"或 token 持久化功能。」

#### 听写模式（右 Alt）

语音原文直接追加到当前输入位置，不经过 AI 处理，速度更快。

| 步骤 | 说明 |
|------|------|
| 1 | 光标定位到任意输入框，按**右 Alt** 开始录音 |
| 2 | 说话，状态条显示「听写（录音中）」 |
| 3 | 再按**右 Alt** 停止，转录文字直接追加，状态条消失 |

### 典型使用场景

- **Vibe coding / 与 AI 对话**：口述复杂需求，整理成精准 prompt
- **AI 短剧创作**：说出剧情想法，整理成结构化的剧情设计
- **工作沟通**：口头说明任务，输出条理清晰的说明文字
- **记录想法**：灵感说出来，整理成可读笔记

### 安装与运行

**系统要求**：Windows 10 / 11（64 位）

```powershell
# 初始化（仅首次，下载模型约 3GB）
.\setup.ps1

# 启动
.\desktop.ps1
```

或直接双击 `启动 Voice Prompt Tool.exe`。

### 模型说明

| 组件 | 模型 | 用途 |
|------|------|------|
| 语音识别（中文） | SenseVoice Small | 语音转文字 |
| 语音识别（英文） | Whisper medium | 语音转文字 |
| AI 润色 | Qwen3（本地） | 口语改写为书面表达 |

### 技术栈

- **GUI**：PySide6（Qt）
- **语音识别**：FunASR / SenseVoice · faster-whisper
- **AI 推理**：Ollama + Qwen3
- **文字注入**：Win32 API（SendMessage）
- **全局热键**：WH_KEYBOARD_LL 低级键盘钩子

---

## License / 开源协议

MIT License — free to use, modify, and distribute. / 免费使用、修改、分发。

---

## Feedback / 反馈

Issues and PRs welcome! If this tool is useful to you, a ⭐ Star is the best encouragement.

欢迎提 Issue 和 PR！如果这个工具对你有帮助，点个 Star ⭐ 是最大的支持。
