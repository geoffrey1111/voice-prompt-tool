# Voice Prompt Tool

**说话，它来整理** — 在任意输入框按下快捷键，用声音代替打字。口语随便说，输出逻辑清晰的书面文字。

> Voice-to-text tool for Windows. Press a hotkey in any text field, speak naturally, get clean organized text — powered by local ASR + Qwen AI, fully offline.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 功能特点

- **任意输入框可用** — 微信、浏览器、记事本、代码编辑器，按键即用
- **两种模式**：AI 润色模式 + 极速听写模式
- **完全本地运行** — 语音识别与 AI 均在本机执行，无需联网，数据不外传
- **后台常驻无感知** — 系统托盘驻留，不占前台窗口

---

## 两种使用模式

### AI 模式（Ctrl + Space）

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

### 听写模式（右 Alt）

语音原文直接追加到当前输入位置，不经过 AI 处理，速度更快。

| 步骤 | 说明 |
|------|------|
| 1 | 光标定位到任意输入框，按**右 Alt** 开始录音 |
| 2 | 说话，状态条显示「听写（录音中）」 |
| 3 | 再按**右 Alt** 停止，转录文字直接追加，状态条消失 |

---

## 典型使用场景

- **与 AI 对话**：口述复杂需求，整理成精准 prompt，提升 AI 理解质量
- **工作沟通**：口头说明任务对接，输出条理清晰的说明文字，直接发给同事
- **记录想法**：灵感说出来，整理成可读笔记或草稿

---

## 安装与运行

### 系统要求

- Windows 10 / 11（64 位）
- 首次启动需联网下载模型（约 3GB），之后完全离线运行

### 快速开始

1. 下载最新 Release，解压到任意目录
2. 运行 `setup.ps1` 完成环境初始化和模型下载
3. 双击 `启动 Voice Prompt Tool.exe` 或运行 `desktop.ps1`
4. 系统托盘出现图标即代表运行成功
5. 在任意输入框按 **Ctrl+Space** 开始使用

```powershell
# 初始化（仅首次）
.\setup.ps1

# 启动
.\desktop.ps1
```

### 模型说明

| 组件 | 模型 | 用途 |
|------|------|------|
| 语音识别（ASR） | SenseVoice Small | 语音转文字 |
| AI 润色 | Qwen3（本地） | 口语改写为书面表达 |

---

## 技术栈

- **GUI**：PySide6（Qt）
- **语音识别**：FunASR / SenseVoice
- **AI 推理**：Ollama + Qwen3
- **文字注入**：Win32 API（SendMessage / UpdateResource）
- **全局热键**：WH_KEYBOARD_LL 低级键盘钩子

---

## 开源协议

MIT License — 免费使用、修改、分发。

---

## 反馈与贡献

欢迎提 Issue 和 PR！如果这个工具对你有帮助，点个 Star ⭐ 是最大的支持。
