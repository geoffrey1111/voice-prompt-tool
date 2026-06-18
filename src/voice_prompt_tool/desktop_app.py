from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRectF, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from voice_prompt_tool.desktop_recorder import PauseableAudioRecorder, RecorderState
from voice_prompt_tool.desktop_settings import (
    DesktopSettings,
    StartupRegistration,
    load_settings,
    save_settings,
)
from voice_prompt_tool.desktop_warmup import DesktopModelWarmup
from voice_prompt_tool.desktop_text_injection import DictationSession, TextInjector
from voice_prompt_tool.paths import DEFAULT_ROOT, configure_cache_environment, ensure_runtime_dirs
from voice_prompt_tool.pipeline import VoicePromptResult


_STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "pill_ai_recording":        "AI模式（录音中）",
        "pill_dictation_recording": "听写（录音中）",
        "pill_transcribing":        "识别中",
        "pill_processing":          "处理中",
        "pill_model_loading":       "模型加载中",
        "menu_record_ai":           "开始录音并整理",
        "menu_dictation":           "快速听写",
        "menu_rewrite_panel":       "整理文字...",
        "menu_settings":            "设置",
        "menu_load_models":         "预热模型",
        "menu_release_models":      "释放模型",
        "menu_open_logs":           "打开日志目录",
        "menu_quit":                "退出",
        "notif_loading_title":      "模型正在加载",
        "notif_loading_body":       "加载完成后才能开始录音。",
        "notif_ready_title":        "模型已加载完成",
        "notif_ready_body":         "现在可以使用快捷键开始录音或听写。",
        "notif_released_title":     "模型已释放",
        "notif_released_body":      "如需继续使用，请先预热模型；热键会先进入加载状态。",
        "tooltip_loading":          "Voice Prompt Tool - 模型加载中",
        "tooltip_ready":            "Voice Prompt Tool - 模型已就绪",
        "tooltip_released":         "Voice Prompt Tool - 模型已释放",
        "tooltip_not_loaded":       "Voice Prompt Tool - 模型未加载",
        "settings_title":           "设置",
        "settings_startup_check":   "开机后自动在后台启动",
        "settings_startup_label":   "开机自启动",
        "settings_warmup_check":    "启动后自动加载 ASR 和 Qwen",
        "settings_warmup_label":    "启动预热",
        "settings_warmup_tip":      "当前版本固定在启动后加载模型，加载完成后才允许录音。",
        "settings_idle_label":      "空闲释放",
        "settings_idle_never":      "不自动释放",
        "settings_idle_10":         "空闲 10 分钟后释放",
        "settings_idle_30":         "空闲 30 分钟后释放",
        "settings_idle_60":         "空闲 60 分钟后释放",
        "settings_style_label":     "整理强度",
        "settings_style_faithful":  "忠实整理",
        "settings_style_concise":   "简洁整理",
        "settings_style_semantic":  "强理解转述（推荐）",
        "settings_lang_label":      "语言 / Language",
        "settings_lang_tip":        "切换语言后需重新加载模型。English 模式下载 Whisper medium 模型（约 1.5 GB）。",
        "settings_hotkey_ai_label":        "AI 模式快捷键",
        "settings_hotkey_dictation_label": "听写模式快捷键",
        "settings_hotkey_conflict":        "AI 快捷键和听写快捷键不能相同，请重新选择。",
        "settings_btn_refresh":     "刷新状态",
        "settings_btn_load":        "预热模型",
        "settings_btn_release":     "释放模型",
        "settings_btn_logs":        "打开日志目录",
        "settings_status_prefix":   "模型状态：",
        "settings_paths":           "模型目录：{ollama}\nASR目录：{asr}\n录音目录：{rec}\n日志目录：{logs}",
        "panel_title":              "文字整理",
        "panel_input_label":        "粘贴要整理的文字：",
        "panel_input_placeholder":  "Ctrl+V 粘贴进来……",
        "panel_btn_rewrite":        "AI 整理 ↓",
        "panel_btn_rewriting":      "整理中…",
        "panel_output_label":       "整理结果：",
        "panel_output_placeholder": "整理后的结果会出现在这里……",
        "panel_btn_copy":           "复制结果",
        "panel_btn_copied":         "已复制 ✓",
        "panel_model_not_ready":    "模型尚未加载完成，请稍等后重试。",
        "panel_rewrite_failed":     "整理失败：",
    },
    "en": {
        "pill_ai_recording":        "AI mode (recording)",
        "pill_dictation_recording": "Dictation (recording)",
        "pill_transcribing":        "Transcribing",
        "pill_processing":          "Processing",
        "pill_model_loading":       "Loading models",
        "menu_record_ai":           "Record && Rewrite",
        "menu_dictation":           "Quick Dictation",
        "menu_rewrite_panel":       "Rewrite Text...",
        "menu_settings":            "Settings",
        "menu_load_models":         "Load Models",
        "menu_release_models":      "Release Models",
        "menu_open_logs":           "Open Log Folder",
        "menu_quit":                "Quit",
        "notif_loading_title":      "Loading Models",
        "notif_loading_body":       "Please wait until models are loaded.",
        "notif_ready_title":        "Models Ready",
        "notif_ready_body":         "Ready. Use your configured hotkeys to record or dictate.",
        "notif_released_title":     "Models Released",
        "notif_released_body":      "Reload models from the tray menu to continue.",
        "tooltip_loading":          "Voice Prompt Tool - Loading",
        "tooltip_ready":            "Voice Prompt Tool - Ready",
        "tooltip_released":         "Voice Prompt Tool - Released",
        "tooltip_not_loaded":       "Voice Prompt Tool - Not loaded",
        "settings_title":           "Settings",
        "settings_startup_check":   "Launch automatically at Windows startup",
        "settings_startup_label":   "Auto-start",
        "settings_warmup_check":    "Load ASR and Qwen on startup",
        "settings_warmup_label":    "Model warmup",
        "settings_warmup_tip":      "Models are always loaded at startup in the current version.",
        "settings_idle_label":      "Idle release",
        "settings_idle_never":      "Never release",
        "settings_idle_10":         "Release after 10 min idle",
        "settings_idle_30":         "Release after 30 min idle",
        "settings_idle_60":         "Release after 60 min idle",
        "settings_style_label":     "Rewrite style",
        "settings_style_faithful":  "Faithful",
        "settings_style_concise":   "Concise",
        "settings_style_semantic":  "Semantic (Recommended)",
        "settings_lang_label":      "Language / 语言",
        "settings_lang_tip":        "Switching language reloads models. English mode downloads Whisper medium (~1.5 GB).",
        "settings_hotkey_ai_label":        "AI Mode Hotkey",
        "settings_hotkey_dictation_label": "Dictation Hotkey",
        "settings_hotkey_conflict":        "AI hotkey and Dictation hotkey must be different. Please choose again.",
        "settings_btn_refresh":     "Refresh",
        "settings_btn_load":        "Load Models",
        "settings_btn_release":     "Release",
        "settings_btn_logs":        "Open Logs",
        "settings_status_prefix":   "Model status: ",
        "settings_paths":           "Model dir: {ollama}\nASR dir: {asr}\nRecording dir: {rec}\nLog dir: {logs}",
        "panel_title":              "Text Rewrite",
        "panel_input_label":        "Paste text to rewrite:",
        "panel_input_placeholder":  "Paste your text here...",
        "panel_btn_rewrite":        "AI Rewrite ↓",
        "panel_btn_rewriting":      "Rewriting...",
        "panel_output_label":       "Result:",
        "panel_output_placeholder": "The rewritten result will appear here...",
        "panel_btn_copy":           "Copy Result",
        "panel_btn_copied":         "Copied ✓",
        "panel_model_not_ready":    "Models not ready yet. Please wait and try again.",
        "panel_rewrite_failed":     "Rewrite failed: ",
    },
}


def _t(key: str, lang: str) -> str:
    return _STRINGS.get(lang, _STRINGS["zh"]).get(key, _STRINGS["zh"].get(key, key))


WM_HOTKEY = 0x0312
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
MOD_CONTROL = 0x0002
WH_KEYBOARD_LL = 13
LLKHF_EXTENDED = 0x01
VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_SPACE = 0x20
VK_MENU = 0x12
VK_RMENU = 0xA5
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
HOTKEY_AI = 61015
HOTKEY_DICTATION = 61016
SYNTHETIC_EXTRA_INFO = 1  # marker on our own SendInput events so the hook skips them

# ---------------------------------------------------------------------------
# Hotkey parsing helpers
# ---------------------------------------------------------------------------
_VK_FROM_NAME: dict[str, int] = {
    "space": VK_SPACE,
    "enter": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    **{chr(0x41 + i).lower(): 0x41 + i for i in range(26)},   # a=0x41 … z=0x5A
    **{str(i): 0x30 + i for i in range(10)},                   # 0–9
    **{f"f{i}": 0x6F + i for i in range(1, 13)},               # f1=0x70 … f12=0x7B
}

_MOD_NAMES = frozenset({"ctrl", "shift", "alt"})


def _parse_hotkey(s: str) -> tuple[frozenset[str], int] | None:
    """Parse "ctrl+space" → (frozenset({"ctrl"}), VK_SPACE). None if invalid."""
    parts = [p.strip().lower() for p in s.split("+") if p.strip()]
    mods: set[str] = set()
    vk: int | None = None
    for p in parts:
        if p in _MOD_NAMES:
            mods.add(p)
        elif p in _VK_FROM_NAME:
            if vk is not None:
                return None
            vk = _VK_FROM_NAME[p]
        else:
            return None
    if vk is None:
        return None
    return frozenset(mods), vk


def _format_hotkey(s: str) -> str:
    """Human-readable label: "ctrl+space" → "Ctrl + Space", "right_alt" → "Right Alt"."""
    if s == "right_alt":
        return "Right Alt"
    _display = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "space": "Space",
                "enter": "Enter", "tab": "Tab", "backspace": "Backspace"}
    parts = [p.strip().lower() for p in s.split("+") if p.strip()]
    return " + ".join(_display.get(p, p.upper() if len(p) == 1 else p.title()) for p in parts)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
# On 64-bit Windows, WPARAM/LPARAM/LRESULT are 64-bit; ctypes.wintypes uses c_long (32-bit)
# which causes OverflowError in CallNextHookEx. Use pointer-sized types instead.
_PTR_SIGNED   = ctypes.c_longlong  if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
_PTR_UNSIGNED = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = _PTR_SIGNED
HOOK_CALLBACK = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    LRESULT,
    ctypes.c_int,   # nCode
    _PTR_UNSIGNED,  # wParam (WPARAM = pointer-sized unsigned)
    _PTR_SIGNED,    # lParam (LPARAM = pointer-sized signed)
)
# Pre-configure CallNextHookEx argtypes to avoid runtime overflow on 64-bit
ctypes.windll.user32.CallNextHookEx.restype  = LRESULT
ctypes.windll.user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,  # hhk
    ctypes.c_int,     # nCode
    _PTR_UNSIGNED,    # wParam
    _PTR_SIGNED,      # lParam
]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


PILL_STYLE = """
QMainWindow#voicePromptWindow {
    background: transparent;
}
QWidget#pillContainer { background: transparent; }
QLabel#pillLabel {
    color: #ffffff;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}
"""

PILL_BG_COLOR = QColor("#101827")


class PillContainer(QWidget):
    """Paints a rounded-capsule background; CSS border-radius is not reliable on Windows."""

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        r = self.height() / 2.0
        path.addRoundedRect(QRectF(self.rect()), r, r)
        painter.fillPath(path, PILL_BG_COLOR)


# Settings dialog uses its own style
SETTINGS_STYLE = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
}
"""


def app_icon_for_root(root: Path) -> QIcon:
    root = Path(root)
    for relative_path in ("icon.png", "assets/app-icon.ico", "assets/app-icon.png"):
        icon_path = root / relative_path
        if icon_path.exists():
            return QIcon(str(icon_path))
    return QIcon()


def open_folder(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]


def tool_memory_summary(root: Path) -> str:
    root_text = str(Path(root))
    script = (
        "$root = $args[0]; "
        "$rows = @(); "
        "foreach ($p in Get-Process) { "
        "  if (-not $p.Path) { continue }; "
        "  if ($p.Path.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) { "
        "    $rows += [PSCustomObject]@{ Name=$p.ProcessName; MB=[Math]::Round($p.WorkingSet64/1MB,1) } "
        "  } "
        "}; "
        "if ($rows.Count -eq 0) { '无本工具进程' } "
        "else { ($rows | ForEach-Object { \"$($_.Name): $($_.MB) MB\" }) -join '; ' }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script, root_text],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "资源占用：暂不可用"
    summary = completed.stdout.strip() or "无本工具进程"
    return f"资源占用：{summary}"


class SettingsDialog(QDialog):
    def __init__(
        self,
        root: Path,
        settings: DesktopSettings,
        model_warmup: DesktopModelWarmup,
        startup_registration: StartupRegistration,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.root = Path(root)
        self.settings = settings
        self.model_warmup = model_warmup
        self.startup_registration = startup_registration
        self.setWindowTitle(_t("settings_title", settings.asr_language))
        self.setMinimumWidth(520)
        self.setStyleSheet(SETTINGS_STYLE)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        lang = self.settings.asr_language
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.startup_checkbox = QCheckBox(_t("settings_startup_check", lang))
        self.startup_checkbox.setChecked(self.settings.start_with_windows or self.startup_registration.is_enabled())
        form.addRow(_t("settings_startup_label", lang), self.startup_checkbox)

        self.auto_prewarm_checkbox = QCheckBox(_t("settings_warmup_check", lang))
        self.auto_prewarm_checkbox.setChecked(True)
        self.auto_prewarm_checkbox.setEnabled(False)
        self.auto_prewarm_checkbox.setToolTip(_t("settings_warmup_tip", lang))
        form.addRow(_t("settings_warmup_label", lang), self.auto_prewarm_checkbox)

        self.idle_release_combo = QComboBox()
        for label, value in (
            (_t("settings_idle_never", lang), 0),
            (_t("settings_idle_10", lang), 10),
            (_t("settings_idle_30", lang), 30),
            (_t("settings_idle_60", lang), 60),
        ):
            self.idle_release_combo.addItem(label, value)
        self.idle_release_combo.setCurrentIndex(max(0, self.idle_release_combo.findData(self.settings.idle_release_minutes)))
        form.addRow(_t("settings_idle_label", lang), self.idle_release_combo)

        self.rewrite_style_combo = QComboBox()
        for label, value in (
            (_t("settings_style_faithful", lang), "faithful"),
            (_t("settings_style_concise", lang), "concise"),
            (_t("settings_style_semantic", lang), "semantic"),
        ):
            self.rewrite_style_combo.addItem(label, value)
        self.rewrite_style_combo.setCurrentIndex(max(0, self.rewrite_style_combo.findData(self.settings.rewrite_style)))
        form.addRow(_t("settings_style_label", lang), self.rewrite_style_combo)

        self.language_combo = QComboBox()
        for label, value in (
            ("中文（SenseVoice · 推荐）", "zh"),
            ("English（Whisper medium）", "en"),
        ):
            self.language_combo.addItem(label, value)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.asr_language)))
        self.language_combo.setToolTip(_t("settings_lang_tip", lang))
        form.addRow(_t("settings_lang_label", lang), self.language_combo)

        self.hotkey_ai_btn = HotkeyButton(self.settings.hotkey_ai, lang=lang)
        form.addRow(_t("settings_hotkey_ai_label", lang), self.hotkey_ai_btn)

        self.hotkey_dictation_btn = HotkeyButton(self.settings.hotkey_dictation, lang=lang)
        form.addRow(_t("settings_hotkey_dictation_label", lang), self.hotkey_dictation_btn)

        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.path_label = QLabel(
            _t("settings_paths", lang).format(
                ollama=self.root / "ollama-models",
                asr=self.root / "cache" / "hf-models" / "SenseVoiceSmall",
                rec=self.root / "recordings",
                logs=self.root / "logs",
            )
        )
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton(_t("settings_btn_refresh", lang))
        self.refresh_button.clicked.connect(self.refresh_status)
        button_row.addWidget(self.refresh_button)

        self.prewarm_button = QPushButton(_t("settings_btn_load", lang))
        self.prewarm_button.clicked.connect(self.prewarm_models)
        button_row.addWidget(self.prewarm_button)

        self.release_button = QPushButton(_t("settings_btn_release", lang))
        self.release_button.clicked.connect(self.release_models)
        button_row.addWidget(self.release_button)

        self.logs_button = QPushButton(_t("settings_btn_logs", lang))
        self.logs_button.clicked.connect(lambda: open_folder(self.root / "logs"))
        button_row.addWidget(self.logs_button)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh_status(self) -> None:
        lang = self.settings.asr_language
        self.status_label.setText(f"{_t('settings_status_prefix', lang)}{self.model_warmup.status_text}\n{tool_memory_summary(self.root)}")

    def prewarm_models(self) -> None:
        self.model_warmup.start()
        self.refresh_status()

    def release_models(self) -> None:
        self.model_warmup.release()
        self.refresh_status()

    def accept(self) -> None:
        new_ai_hotkey = self.hotkey_ai_btn.hotkey
        new_dictation_hotkey = self.hotkey_dictation_btn.hotkey
        if new_ai_hotkey == new_dictation_hotkey:
            lang = self.settings.asr_language
            QMessageBox.warning(self, _t("settings_title", lang), _t("settings_hotkey_conflict", lang))
            return
        self.settings.start_with_windows = self.startup_checkbox.isChecked()
        self.settings.auto_prewarm = True
        self.settings.idle_release_minutes = int(self.idle_release_combo.currentData())
        self.settings.rewrite_style = str(self.rewrite_style_combo.currentData())
        self.settings.asr_language = str(self.language_combo.currentData())
        self.settings.hotkey_ai = new_ai_hotkey
        self.settings.hotkey_dictation = new_dictation_hotkey
        if self.settings.start_with_windows:
            self.startup_registration.enable()
        else:
            self.startup_registration.disable()
        save_settings(self.root, self.settings)
        super().accept()


class RightAltKeyboardHook(QObject):
    activated = Signal()    # dictation hotkey pressed
    ctrl_space = Signal()   # AI hotkey pressed

    def __init__(
        self,
        ai_hotkey: str = "ctrl+space",
        dictation_hotkey: str = "right_alt",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._hook_handle = None
        self._ctrl_down = False
        self._shift_down = False
        self._ai_down = False
        self._dictation_combo_down = False
        self._right_alt_down = False
        self._callback = HOOK_CALLBACK(self._keyboard_proc)
        self.set_hotkeys(ai_hotkey, dictation_hotkey)

    def set_hotkeys(self, ai_hotkey: str, dictation_hotkey: str) -> None:
        parsed_ai = _parse_hotkey(ai_hotkey)
        self._ai_mods: frozenset[str] = parsed_ai[0] if parsed_ai else frozenset({"ctrl"})
        self._ai_vk: int = parsed_ai[1] if parsed_ai else VK_SPACE

        self._dictation_is_right_alt = dictation_hotkey == "right_alt"
        if self._dictation_is_right_alt:
            self._dictation_mods: frozenset[str] = frozenset()
            self._dictation_vk: int | None = None
        else:
            parsed_d = _parse_hotkey(dictation_hotkey)
            self._dictation_mods = parsed_d[0] if parsed_d else frozenset()
            self._dictation_vk = parsed_d[1] if parsed_d else None

        # Reset tracking state when hotkeys change
        self._ai_down = False
        self._dictation_combo_down = False
        self._right_alt_down = False

    def install(self) -> None:
        if self._hook_handle:
            return
        hook_handle = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._callback,
            None,
            0,
        )
        if not hook_handle:
            raise RuntimeError("右 Alt 快捷键监听失败，可能被系统安全策略或其他程序拦截。")
        self._hook_handle = hook_handle

    def uninstall(self) -> None:
        if not self._hook_handle:
            return
        ctypes.windll.user32.UnhookWindowsHookEx(self._hook_handle)
        self._hook_handle = None
        self._right_alt_down = False

    def _keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0 and l_param:
            event = KBDLLHOOKSTRUCT.from_address(int(l_param))
            if event.dwExtraInfo == SYNTHETIC_EXTRA_INFO:
                return ctypes.windll.user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)
            if self._handle_key_event(int(event.vkCode), int(event.flags), int(w_param)):
                return 1
        return ctypes.windll.user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

    def _handle_key_event(self, vk_code: int, flags: int, message: int) -> bool:
        actual_ctrl = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

        if vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
            self._ctrl_down = message in (WM_KEYDOWN, WM_SYSKEYDOWN)
            return False

        if vk_code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            self._shift_down = message in (WM_KEYDOWN, WM_SYSKEYDOWN)
            return False

        if self._ctrl_down and not actual_ctrl:
            self._ctrl_down = False
            self._ai_down = False
            self._dictation_combo_down = False

        is_down = message in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = message in (WM_KEYUP, WM_SYSKEYUP)

        # AI hotkey
        if vk_code == self._ai_vk:
            if is_down and self._mods_match(self._ai_mods) and not self._ai_down:
                self._ai_down = True
                self.ctrl_space.emit()
                return True
            if is_up and self._ai_down:
                self._ai_down = False
                return True

        # Dictation combo hotkey (non-right-alt)
        if (not self._dictation_is_right_alt
                and self._dictation_vk is not None
                and vk_code == self._dictation_vk):
            if is_down and self._mods_match(self._dictation_mods) and not self._dictation_combo_down:
                self._dictation_combo_down = True
                self.activated.emit()
                return True
            if is_up and self._dictation_combo_down:
                self._dictation_combo_down = False
                return True

        # Right Alt dictation
        if self._dictation_is_right_alt and self._is_right_alt(vk_code, flags):
            if is_down:
                if self._right_alt_down:
                    return True
                self._right_alt_down = True
                self.activated.emit()
                return True
            if is_up:
                was_down = self._right_alt_down
                self._right_alt_down = False
                return was_down

        return False

    def _mods_match(self, required: frozenset[str]) -> bool:
        return self._ctrl_down == ("ctrl" in required) and self._shift_down == ("shift" in required)

    @staticmethod
    def _is_right_alt(vk_code: int, flags: int) -> bool:
        return vk_code == VK_RMENU or (vk_code == VK_MENU and bool(flags & LLKHF_EXTENDED))


class GlobalHotkeyReceiver(QWidget):
    activated = Signal()
    dictation_activated = Signal()

    def __init__(self, ai_hotkey: str = "ctrl+space", dictation_hotkey: str = "right_alt") -> None:
        super().__init__()
        self._registered = False
        self._right_alt_hook = RightAltKeyboardHook(ai_hotkey, dictation_hotkey, self)
        self._right_alt_hook.ctrl_space.connect(self.activated.emit)
        self._right_alt_hook.activated.connect(self.dictation_activated.emit)

    def set_hotkeys(self, ai_hotkey: str, dictation_hotkey: str) -> None:
        self._right_alt_hook.set_hotkeys(ai_hotkey, dictation_hotkey)

    def register(self) -> None:
        if self._registered:
            return
        self._right_alt_hook.install()
        self._registered = True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._right_alt_hook.uninstall()
        self._registered = False

    def closeEvent(self, event: QCloseEvent) -> None:
        self.unregister()
        super().closeEvent(event)


class ProcessingThread(QThread):
    transcript_ready = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        audio_path: Path,
        root: Path,
        model_warmup: DesktopModelWarmup | None = None,
        mode: str = "ai",
    ) -> None:
        super().__init__()
        self.audio_path = Path(audio_path)
        self.root = Path(root)
        self.model_warmup = model_warmup
        self.mode = mode

    def run(self) -> None:
        try:
            if self.model_warmup is None or not self.model_warmup.is_ready:
                raise RuntimeError("模型尚未加载完成，请等待预热结束后再使用。")
            if self.mode == "dictation":
                result = self.model_warmup.transcribe_only(self.audio_path)
            else:
                result = self.model_warmup.process(
                    self.audio_path,
                    on_transcript=self.transcript_ready.emit,
                )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class RewriteSelectionThread(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, text: str, model_warmup: DesktopModelWarmup, parent=None) -> None:
        super().__init__(parent)
        self.text = text
        self.model_warmup = model_warmup

    def run(self) -> None:
        try:
            result = self.model_warmup.rewrite_text(self.text)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


PANEL_STYLE = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}
QPlainTextEdit {
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 6px;
    background: #fafafa;
}
QPlainTextEdit[readOnly="true"] {
    background: #f0f4f8;
}
QPushButton {
    border-radius: 6px;
    padding: 6px 16px;
    background: #1a73e8;
    color: white;
    font-weight: 600;
    border: none;
}
QPushButton:hover { background: #1558b0; }
QPushButton:disabled { background: #c0c8d0; color: #888; }
QPushButton#copyBtn {
    background: #34a853;
}
QPushButton#copyBtn:hover { background: #1e7e34; }
QPushButton#copyBtn:disabled { background: #c0c8d0; color: #888; }
"""


class HotkeyButton(QPushButton):
    """Click to enter capture mode, then press any key combination to record it as a hotkey.

    Supported combinations:
    - Ctrl + key  (e.g. Ctrl+Space, Ctrl+Shift+R)
    - Right Alt   (standalone)
    Press Escape to cancel capture without changing the hotkey.
    """

    hotkey_changed = Signal(str)

    def __init__(self, hotkey: str, lang: str = "zh", parent=None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._lang = lang
        self._capturing = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(170)
        self._update_display()
        self.clicked.connect(self._start_capture)

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def _start_capture(self) -> None:
        self._capturing = True
        self.setText("按下快捷键…" if self._lang == "zh" else "Press keys…")
        self.setFocus()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if not self._capturing:
            return super().keyPressEvent(event)
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._capturing = False
            self._update_display()
            return

        # Right Alt — check native VK or extended scan code
        if key == Qt.Key.Key_Alt:
            native_vk = event.nativeVirtualKey()
            native_scan = event.nativeScanCode()
            if native_vk == 0xA5 or (native_scan & 0x100):  # VK_RMENU or extended alt
                self._finish_capture("right_alt")
            return  # ignore Left Alt

        # Ignore other standalone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return

        # Build modifier prefix — Ctrl required for combos
        mods = event.modifiers()
        parts: list[str] = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if "ctrl" not in parts:
            return  # combos without Ctrl are too risky; stay in capture mode

        key_name = self._resolve_key(key, event.nativeVirtualKey())
        if key_name:
            parts.append(key_name)
            self._finish_capture("+".join(parts))

    def _finish_capture(self, hotkey: str) -> None:
        self._hotkey = hotkey
        self._capturing = False
        self._update_display()
        self.hotkey_changed.emit(hotkey)

    @staticmethod
    def _resolve_key(qt_key: int, native_vk: int) -> str | None:
        vk_to_name = {v: k for k, v in _VK_FROM_NAME.items()}
        if native_vk in vk_to_name:
            return vk_to_name[native_vk]
        # Qt key fallback
        if 65 <= qt_key <= 90:   # Key_A … Key_Z match ASCII uppercase
            return chr(qt_key + 32)
        if 48 <= qt_key <= 57:   # Key_0 … Key_9
            return str(qt_key - 48)
        if qt_key == Qt.Key.Key_Space:
            return "space"
        return None

    def _update_display(self) -> None:
        self.setText(_format_hotkey(self._hotkey))

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        if self._capturing:
            self._capturing = False
            self._update_display()
        super().focusOutEvent(event)


class TextRewritePanel(QWidget):
    """Floating panel: paste text → AI rewrites → copy result. Independent of voice flow."""

    def __init__(
        self,
        model_warmup: DesktopModelWarmup,
        settings_provider: Callable[[], DesktopSettings] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model_warmup = model_warmup
        self._settings_provider = settings_provider or DesktopSettings
        self._thread: RewriteSelectionThread | None = None
        self.setWindowIcon(QIcon())
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(440, 380)
        self.resize(480, 460)
        self.setStyleSheet(PANEL_STYLE)
        self._build_ui()

    def _lang(self) -> str:
        return self._settings_provider().asr_language

    def _build_ui(self) -> None:
        lang = self._lang()
        self.setWindowTitle(_t("panel_title", lang))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._input_label = QLabel(_t("panel_input_label", lang))
        layout.addWidget(self._input_label)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText(_t("panel_input_placeholder", lang))
        self.input_edit.setMinimumHeight(120)
        layout.addWidget(self.input_edit, stretch=1)

        self.rewrite_btn = QPushButton(_t("panel_btn_rewrite", lang))
        self.rewrite_btn.setMinimumHeight(36)
        self.rewrite_btn.clicked.connect(self._start_rewrite)
        layout.addWidget(self.rewrite_btn)

        self._output_label = QLabel(_t("panel_output_label", lang))
        layout.addWidget(self._output_label)

        self.output_edit = QPlainTextEdit()
        self.output_edit.setPlaceholderText(_t("panel_output_placeholder", lang))
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(120)
        layout.addWidget(self.output_edit, stretch=1)

        self.copy_btn = QPushButton(_t("panel_btn_copy", lang))
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setMinimumHeight(36)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_result)
        layout.addWidget(self.copy_btn)

    def retranslate(self) -> None:
        lang = self._lang()
        self.setWindowTitle(_t("panel_title", lang))
        self._input_label.setText(_t("panel_input_label", lang))
        self.input_edit.setPlaceholderText(_t("panel_input_placeholder", lang))
        self._output_label.setText(_t("panel_output_label", lang))
        self.output_edit.setPlaceholderText(_t("panel_output_placeholder", lang))
        if self.rewrite_btn.isEnabled():
            self.rewrite_btn.setText(_t("panel_btn_rewrite", lang))
        if self.copy_btn.isEnabled():
            self.copy_btn.setText(_t("panel_btn_copy", lang))

    def _start_rewrite(self) -> None:
        lang = self._lang()
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if not self.model_warmup.is_ready:
            self.output_edit.setPlainText(_t("panel_model_not_ready", lang))
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self.rewrite_btn.setEnabled(False)
        self.rewrite_btn.setText(_t("panel_btn_rewriting", lang))
        self.output_edit.clear()
        self.copy_btn.setEnabled(False)
        self._thread = RewriteSelectionThread(text, self.model_warmup)
        self._thread.completed.connect(self._on_completed)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_completed(self, result: str) -> None:
        lang = self._lang()
        self._thread = None
        self.output_edit.setPlainText(result)
        self.rewrite_btn.setEnabled(True)
        self.rewrite_btn.setText(_t("panel_btn_rewrite", lang))
        self.copy_btn.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        lang = self._lang()
        self._thread = None
        self.output_edit.setPlainText(f"{_t('panel_rewrite_failed', lang)}{message}")
        self.rewrite_btn.setEnabled(True)
        self.rewrite_btn.setText(_t("panel_btn_rewrite", lang))

    def _copy_result(self) -> None:
        lang = self._lang()
        text = self.output_edit.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copy_btn.setText(_t("panel_btn_copied", lang))
        QTimer.singleShot(1500, lambda: self.copy_btn.setText(_t("panel_btn_copy", self._lang())))

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()


class ResultWindow(QMainWindow):
    """Compact pill-only recording/processing indicator. Never steals keyboard focus."""

    _STATE_HIDDEN = "hidden"
    _STATE_MODEL_LOADING = "model_loading"
    _STATE_RECORDING = "recording"
    _STATE_ASR = "asr"
    _STATE_PROCESSING = "processing"

    def __init__(
        self,
        root: Path,
        model_warmup: DesktopModelWarmup | None = None,
        settings_provider: Callable[[], DesktopSettings] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("voicePromptWindow")
        self.setStyleSheet(PILL_STYLE)
        self.root = Path(root)
        self.recorder = PauseableAudioRecorder(self.root / "recordings")
        self.model_warmup = model_warmup or DesktopModelWarmup(self.root)
        self._settings_provider = settings_provider or DesktopSettings
        self.last_activity_at = time.monotonic()
        self._processing_thread: ProcessingThread | None = None
        self.recording_mode = "ai"
        self.text_injector = TextInjector()
        self._input_session: DictationSession | None = None
        self._replacement_generation = 0
        self._pill_state = self._STATE_HIDDEN
        self._anim_frame = 0
        # Coordinating insert + replace for AI mode
        self._insert_in_progress = False
        self._pending_final_text: str | None = None
        self._pending_final_gen: int | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowIcon(app_icon_for_root(self.root))
        self._build_pill_ui()

        # Animation timer — cycles dots on the label
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(400)
        self._anim_timer.timeout.connect(self._tick_animation)

        # Topmost keep-alive — re-asserts HWND_TOPMOST without activating
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(200)
        self._topmost_timer.timeout.connect(self._compact_bar_topmost_noactivate)

    # ------------------------------------------------------------------ UI build

    def _build_pill_ui(self) -> None:
        container = PillContainer()
        container.setObjectName("pillContainer")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pill_label = QLabel("")
        self.pill_label.setObjectName("pillLabel")
        self.pill_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.pill_label)
        self.setCentralWidget(container)

    # ------------------------------------------------------------------ pill show/hide

    def _show_pill(self, text: str) -> None:
        """Make pill visible with given text — never steals keyboard focus."""
        self.pill_label.setText(text)
        self._sync_pill_geometry()
        if not self.isVisible():
            self.show()
        self._compact_bar_topmost_noactivate()

    def _hide_pill(self) -> None:
        self._anim_timer.stop()
        self._topmost_timer.stop()
        self._pill_state = self._STATE_HIDDEN
        self.hide()

    def _sync_pill_geometry(self) -> None:
        """Resize window to fit content then reposition."""
        label_hint = self.pill_label.sizeHint()
        m = self.centralWidget().layout().contentsMargins()
        w = label_hint.width() + m.left() + m.right()
        h = label_hint.height() + m.top() + m.bottom()
        self.resize(w, h)
        self._position_pill()

    def _position_pill(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = available.left() + (available.width() - self.width()) // 2
        y = available.bottom() - self.height() - 20
        self.move(x, y)

    def _compact_bar_topmost_noactivate(self) -> None:
        """Re-assert pill as topmost visible window without stealing keyboard focus."""
        ctypes.windll.user32.SetWindowPos(
            int(self.winId()),
            ctypes.c_void_p(-1),  # HWND_TOPMOST
            0, 0, 0, 0,
            0x0002 | 0x0001 | 0x0010 | 0x0040,  # NOMOVE | NOSIZE | NOACTIVATE | SHOWWINDOW
        )

    # ------------------------------------------------------------------ animation

    def _tick_animation(self) -> None:
        self._anim_frame = (self._anim_frame + 1) % 3
        dots = "•" * (self._anim_frame + 1)
        ellipsis = "." * (self._anim_frame + 1)
        lang = self._settings_provider().asr_language
        if self._pill_state == self._STATE_MODEL_LOADING:
            self.pill_label.setText(f"{_t('pill_model_loading', lang)}{ellipsis}")
        elif self._pill_state == self._STATE_RECORDING:
            key = "pill_ai_recording" if self.recording_mode == "ai" else "pill_dictation_recording"
            self.pill_label.setText(f"{_t(key, lang)}{dots}")
        elif self._pill_state == self._STATE_ASR:
            self.pill_label.setText(f"{_t('pill_transcribing', lang)}{ellipsis}")
        elif self._pill_state == self._STATE_PROCESSING:
            self.pill_label.setText(f"{_t('pill_processing', lang)}{ellipsis}")
        self._sync_pill_geometry()

    # ------------------------------------------------------------------ recording flow

    def start_recording_interaction(self, mode: str = "ai") -> None:
        if self.recorder.state is not RecorderState.IDLE:
            return
        if self._is_processing_running():
            return
        if not self.is_model_ready:
            self.model_warmup.start()
            return
        self.recording_mode = "dictation" if mode == "dictation" else "ai"
        self._input_session = self.text_injector.capture_target(excluded_hwnd=int(self.winId()))
        self._replacement_generation += 1
        self._insert_in_progress = False
        self._pending_final_text = None
        self._pending_final_gen = None
        self.recorder.start()
        self.last_activity_at = time.monotonic()
        self._pill_state = self._STATE_RECORDING
        self._anim_frame = 0
        lang = self._settings_provider().asr_language
        key = "pill_ai_recording" if self.recording_mode == "ai" else "pill_dictation_recording"
        self._show_pill(f"{_t(key, lang)}•")
        self._anim_timer.start()
        self._topmost_timer.start()

    def handle_recording_hotkey(self, mode: str = "ai") -> None:
        if self.recorder.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self.stop_and_process()
            return
        if self._is_processing_running() or self._pill_state != self._STATE_HIDDEN:
            # Already doing something — ignore the hotkey press
            return
        self.start_recording_interaction(mode=mode)

    def show_and_raise(self) -> None:
        """No-op unless pill is currently visible; then just re-assert topmost."""
        if self._pill_state != self._STATE_HIDDEN:
            self._compact_bar_topmost_noactivate()

    def stop_and_process(self) -> None:
        if self.recorder.state not in (RecorderState.RECORDING, RecorderState.PAUSED):
            return
        audio_path = self.recorder.stop()
        self.last_activity_at = time.monotonic()
        self._pill_state = self._STATE_ASR
        self._anim_frame = 0
        self.pill_label.setText("识别中.")
        self._processing_thread = ProcessingThread(
            audio_path, self.root, self.model_warmup, mode=self.recording_mode
        )
        self._processing_thread.transcript_ready.connect(self._show_transcript_stage)
        self._processing_thread.completed.connect(self._show_result)
        self._processing_thread.failed.connect(self._show_error)
        self._processing_thread.finished.connect(self._processing_thread.deleteLater)
        self._processing_thread.start()

    # ------------------------------------------------------------------ processing callbacks

    def _show_transcript_stage(self, result: VoicePromptResult) -> None:
        """Called when ASR finishes; Qwen is still running. AI mode only."""
        if self.recording_mode != "ai" or self._input_session is None:
            return
        asr_text = result.corrected_text or result.raw_text
        self._pill_state = self._STATE_PROCESSING
        self._anim_frame = 0
        self.pill_label.setText("处理中.")
        # Insert ASR text into target and track when insert is done
        self._insert_in_progress = True
        self._do_insert_with_retry(asr_text, retries=0)

    def _do_insert_with_retry(self, text: str, retries: int = 0) -> None:
        ok = self.text_injector.insert_text(self._input_session, text)
        if ok:
            self._insert_in_progress = False
            self._maybe_start_replace()
            return
        if retries < 3:
            QTimer.singleShot(300, lambda: self._do_insert_with_retry(text, retries + 1))
        else:
            # All insert attempts failed; still allow replace to proceed
            self._insert_in_progress = False
            self._maybe_start_replace()

    def _show_result(self, result: VoicePromptResult) -> None:
        self._processing_thread = None
        self.last_activity_at = time.monotonic()

        if self.recording_mode == "dictation":
            self._finish_dictation(result)
            return

        # AI mode: replace the ASR text with the Qwen result
        gen = self._replacement_generation
        final_text = result.optimized_prompt or result.corrected_text or result.raw_text
        self._pending_final_text = final_text
        self._pending_final_gen = gen
        self._maybe_start_replace()

    def _maybe_start_replace(self) -> None:
        """Start the replace only after both insert AND Qwen are done."""
        if self._insert_in_progress:
            return  # insert retries still running; will be called again when done
        if self._pending_final_text is None or self._pending_final_gen is None:
            return  # Qwen not done yet
        gen = self._pending_final_gen
        text = self._pending_final_text
        self._pending_final_text = None
        self._pending_final_gen = None
        # Small delay so the target window has time to process the paste before replace
        QTimer.singleShot(200, lambda: self._do_replace_with_retry(text, gen, retries=0))

    def _do_replace_with_retry(self, text: str, gen: int, retries: int = 0) -> None:
        if gen != self._replacement_generation:
            return  # a new recording started; discard
        ok = self.text_injector.replace_inserted_text(self._input_session, text)
        if ok:
            # Keep pill visible briefly so keyboard events from replace can be processed
            QTimer.singleShot(400, lambda: self._finish_replacement(gen))
            return
        if retries < 3:
            QTimer.singleShot(300, lambda: self._do_replace_with_retry(text, gen, retries + 1))
        else:
            # All replace attempts failed; hide pill anyway (text is in clipboard as fallback)
            self._finish_replacement(gen)

    def _finish_replacement(self, gen: int) -> None:
        if gen != self._replacement_generation:
            return
        self.last_activity_at = time.monotonic()
        self._hide_pill()

    # ------------------------------------------------------------------ dictation flow

    def _finish_dictation(self, result: VoicePromptResult) -> None:
        text = result.corrected_text or result.raw_text
        gen = self._replacement_generation
        # Hide pill, then inject text after OS restores focus to target
        self._hide_pill()
        QTimer.singleShot(100, lambda: self._inject_dictation(text, gen, retries=0))

    def _inject_dictation(self, text: str, gen: int, retries: int = 0) -> None:
        if gen != self._replacement_generation:
            return
        ok = self.text_injector.insert_text(self._input_session, text)
        if ok:
            self.last_activity_at = time.monotonic()
            return
        if retries < 3:
            QTimer.singleShot(300, lambda: self._inject_dictation(text, gen, retries + 1))

    # ------------------------------------------------------------------ error

    def _show_error(self, message: str) -> None:
        self._processing_thread = None
        self.last_activity_at = time.monotonic()
        self._hide_pill()

    # ------------------------------------------------------------------ model status

    def show_model_loading_status(self) -> None:
        if self._pill_state in (self._STATE_RECORDING, self._STATE_ASR, self._STATE_PROCESSING):
            return  # don't interrupt active workflow
        self._pill_state = self._STATE_MODEL_LOADING
        self._anim_frame = 0
        lang = self._settings_provider().asr_language
        self._show_pill(f"{_t('pill_model_loading', lang)}.")
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def show_model_ready_status(self) -> None:
        if self._pill_state == self._STATE_MODEL_LOADING:
            self._hide_pill()

    def show_model_released_status(self) -> None:
        pass

    def refresh_model_status(self) -> None:
        pass

    # ------------------------------------------------------------------ lifecycle

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.recorder.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            try:
                self.recorder.stop()
            except Exception:
                pass
        event.ignore()
        self.hide()

    def shutdown(self) -> None:
        if self.recorder.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            try:
                self.recorder.stop()
            except Exception:
                pass
        self.model_warmup.shutdown()

    # ------------------------------------------------------------------ properties

    @property
    def is_busy(self) -> bool:
        return self.recorder.state in (RecorderState.RECORDING, RecorderState.PAUSED) or self._is_processing_running()

    @property
    def is_model_ready(self) -> bool:
        return bool(getattr(self.model_warmup, "is_ready", False))

    def _is_processing_running(self) -> bool:
        if self._processing_thread is None:
            return False
        try:
            running = self._processing_thread.isRunning()
        except RuntimeError:
            self._processing_thread = None
            return False
        if not running:
            self._processing_thread = None
        return running


class DesktopController:
    def __init__(
        self,
        app: QApplication,
        root: Path,
        enable_hotkey: bool = True,
        show_on_start: bool = True,
        settings: DesktopSettings | None = None,
        model_warmup: DesktopModelWarmup | None = None,
    ) -> None:
        self.app = app
        self.root = Path(root)
        self.settings = settings or load_settings(self.root)
        self.startup_registration = StartupRegistration(self.root)
        self.window = ResultWindow(
            root,
            model_warmup=model_warmup or DesktopModelWarmup(self.root, settings_provider=lambda: self.settings),
            settings_provider=lambda: self.settings,
        )
        self._last_model_state = "unknown"
        self.rewrite_panel = TextRewritePanel(
            self.window.model_warmup,
            settings_provider=lambda: self.settings,
        )
        self.rewrite_panel.setWindowIcon(app_icon_for_root(self.root))
        self.tray = QSystemTrayIcon(app_icon_for_root(self.root), app)
        self.tray.setToolTip("Voice Prompt Tool")
        self.hotkey = (
            GlobalHotkeyReceiver(self.settings.hotkey_ai, self.settings.hotkey_dictation)
            if enable_hotkey and os.name == "nt" else None
        )
        self._build_tray_menu()
        if self.hotkey is not None:
            self.hotkey.activated.connect(lambda: self.handle_recording_hotkey(mode="ai"))
            self.hotkey.dictation_activated.connect(lambda: self.handle_recording_hotkey(mode="dictation"))
            self.hotkey.register()
        self.tray.show()
        self.start_model_warmup(show_window=show_on_start)
        self.idle_timer = QTimer()
        self.idle_timer.setInterval(60000)
        self.idle_timer.timeout.connect(self._release_idle_models_if_needed)
        self.idle_timer.start()
        self.model_status_timer = QTimer()
        self.model_status_timer.setInterval(250)
        self.model_status_timer.timeout.connect(self._refresh_model_status)
        self.model_status_timer.start()

    def open_rewrite_panel(self) -> None:
        self.rewrite_panel.show_and_raise()

    def _lang(self) -> str:
        return self.settings.asr_language

    def _build_tray_menu(self) -> None:
        lang = self._lang()
        menu = QMenu()
        start_action = QAction(_t("menu_record_ai", lang), menu)
        start_action.triggered.connect(lambda: self.handle_recording_hotkey(mode="ai"))
        menu.addAction(start_action)
        dictation_action = QAction(_t("menu_dictation", lang), menu)
        dictation_action.triggered.connect(lambda: self.handle_recording_hotkey(mode="dictation"))
        menu.addAction(dictation_action)
        rewrite_action = QAction(_t("menu_rewrite_panel", lang), menu)
        rewrite_action.triggered.connect(self.open_rewrite_panel)
        menu.addAction(rewrite_action)
        settings_action = QAction(_t("menu_settings", lang), menu)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        prewarm_action = QAction(_t("menu_load_models", lang), menu)
        prewarm_action.triggered.connect(lambda: self.start_model_warmup(show_window=True))
        menu.addAction(prewarm_action)
        release_action = QAction(_t("menu_release_models", lang), menu)
        release_action.triggered.connect(self.release_models_with_notice)
        menu.addAction(release_action)
        logs_action = QAction(_t("menu_open_logs", lang), menu)
        logs_action.triggered.connect(lambda: open_folder(self.root / "logs"))
        menu.addAction(logs_action)
        menu.addSeparator()
        quit_action = QAction(_t("menu_quit", lang), menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

    def open_settings(self) -> None:
        previous_rewrite_style = self.settings.rewrite_style
        previous_asr_language = self.settings.asr_language
        if self.hotkey is not None:
            self.hotkey.unregister()
        try:
            dialog = SettingsDialog(
                root=self.root,
                settings=self.settings,
                model_warmup=self.window.model_warmup,
                startup_registration=self.startup_registration,
                parent=None,
            )
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            if self.hotkey is not None:
                self.hotkey.set_hotkeys(self.settings.hotkey_ai, self.settings.hotkey_dictation)
                self.hotkey.register()
        if not accepted:
            return
        lang_changed = self.settings.asr_language != previous_asr_language
        if self.settings.rewrite_style != previous_rewrite_style or lang_changed:
            self.window.model_warmup.release()
        if lang_changed:
            self._build_tray_menu()
            self.rewrite_panel.retranslate()
        if not self.window.model_warmup.is_ready:
            self.start_model_warmup(show_window=True)

    def handle_recording_hotkey(self, mode: str = "ai") -> None:
        if not self.window.is_model_ready:
            lang = self._lang()
            self.start_model_warmup(show_window=True)
            self.tray.showMessage(
                _t("notif_loading_title", lang),
                _t("notif_loading_body", lang),
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        self.window.handle_recording_hotkey(mode=mode)

    def start_model_warmup(self, show_window: bool = True) -> None:
        self.window.model_warmup.start()
        self._last_model_state = "warming"
        self.tray.setToolTip(_t("tooltip_loading", self._lang()))
        self.window.show_model_loading_status()

    def release_models_with_notice(self) -> None:
        lang = self._lang()
        self.window.model_warmup.release()
        self._last_model_state = "released"
        self.tray.setToolTip(_t("tooltip_released", lang))
        self.tray.showMessage(
            _t("notif_released_title", lang),
            _t("notif_released_body", lang),
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _refresh_model_status(self) -> None:
        lang = self._lang()
        if self.window.model_warmup.is_ready:
            if self._last_model_state == "warming":
                self.window.show_model_ready_status()
                self.tray.showMessage(
                    _t("notif_ready_title", lang),
                    _t("notif_ready_body", lang),
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
            self._last_model_state = "ready"
            self.tray.setToolTip(_t("tooltip_ready", lang))
            return
        if self.window.model_warmup.is_warming:
            self._last_model_state = "warming"
            self.tray.setToolTip(_t("tooltip_loading", lang))
            return
        if self._last_model_state != "released":
            self.tray.setToolTip(_t("tooltip_not_loaded", lang))

    def _release_idle_models_if_needed(self) -> None:
        if self.settings.idle_release_minutes <= 0:
            return
        if self.window.is_busy:
            return
        if not self.window.model_warmup.is_ready:
            return
        idle_seconds = time.monotonic() - self.window.last_activity_at
        if idle_seconds >= self.settings.idle_release_minutes * 60:
            self.release_models_with_notice()

    def shutdown(self) -> None:
        self.idle_timer.stop()
        self.model_status_timer.stop()
        if self.hotkey is not None:
            self.hotkey.unregister()
        self.rewrite_panel.deleteLater()
        self.window.shutdown()
        self.tray.hide()


def build_smoke_window() -> tuple[QApplication, ResultWindow]:
    app = QApplication.instance() or QApplication([])
    window = ResultWindow(DEFAULT_ROOT)
    return app, window


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Voice Prompt Tool desktop app.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--smoke", action="store_true", help="Construct the app without starting the event loop.")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable global Ctrl+Space registration.")
    parser.add_argument("--start-hidden", action="store_true", help="Start in tray/background mode without showing the main window.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    configure_cache_environment(root)
    ensure_runtime_dirs(root)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    if args.smoke:
        ResultWindow(root)
        print("desktop smoke ok")
        return 0

    try:
        controller = DesktopController(app, root, enable_hotkey=not args.no_hotkey, show_on_start=not args.start_hidden)
    except Exception as exc:
        QMessageBox.critical(None, "Voice Prompt Tool", str(exc))
        return 1
    app.aboutToQuit.connect(controller.shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
