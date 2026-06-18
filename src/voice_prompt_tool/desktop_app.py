from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time
from pathlib import Path

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
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self.setStyleSheet(SETTINGS_STYLE)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.startup_checkbox = QCheckBox("开机后自动在后台启动")
        self.startup_checkbox.setChecked(self.settings.start_with_windows or self.startup_registration.is_enabled())
        form.addRow("开机自启动", self.startup_checkbox)

        self.auto_prewarm_checkbox = QCheckBox("启动后自动加载 ASR 和 Qwen")
        self.auto_prewarm_checkbox.setChecked(True)
        self.auto_prewarm_checkbox.setEnabled(False)
        self.auto_prewarm_checkbox.setToolTip("当前版本固定在启动后加载模型，加载完成后才允许录音。")
        form.addRow("启动预热", self.auto_prewarm_checkbox)

        self.idle_release_combo = QComboBox()
        for label, value in (
            ("不自动释放", 0),
            ("空闲 10 分钟后释放", 10),
            ("空闲 30 分钟后释放", 30),
            ("空闲 60 分钟后释放", 60),
        ):
            self.idle_release_combo.addItem(label, value)
        self.idle_release_combo.setCurrentIndex(max(0, self.idle_release_combo.findData(self.settings.idle_release_minutes)))
        form.addRow("空闲释放", self.idle_release_combo)

        self.rewrite_style_combo = QComboBox()
        for label, value in (
            ("忠实整理", "faithful"),
            ("简洁整理", "concise"),
            ("强理解转述（推荐）", "semantic"),
        ):
            self.rewrite_style_combo.addItem(label, value)
        self.rewrite_style_combo.setCurrentIndex(max(0, self.rewrite_style_combo.findData(self.settings.rewrite_style)))
        form.addRow("整理强度", self.rewrite_style_combo)

        self.language_combo = QComboBox()
        for label, value in (
            ("中文（SenseVoice · 推荐）", "zh"),
            ("English（Whisper medium）", "en"),
        ):
            self.language_combo.addItem(label, value)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.asr_language)))
        self.language_combo.setToolTip("切换语言后需重新加载模型。English 模式下载 Whisper medium 模型（约 1.5 GB）。")
        form.addRow("语言 / Language", self.language_combo)

        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.path_label = QLabel(
            f"模型目录：{self.root / 'ollama-models'}\n"
            f"ASR目录：{self.root / 'cache' / 'hf-models' / 'SenseVoiceSmall'}\n"
            f"录音目录：{self.root / 'recordings'}\n"
            f"日志目录：{self.root / 'logs'}"
        )
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("刷新状态")
        self.refresh_button.clicked.connect(self.refresh_status)
        button_row.addWidget(self.refresh_button)

        self.prewarm_button = QPushButton("预热模型")
        self.prewarm_button.clicked.connect(self.prewarm_models)
        button_row.addWidget(self.prewarm_button)

        self.release_button = QPushButton("释放模型")
        self.release_button.clicked.connect(self.release_models)
        button_row.addWidget(self.release_button)

        self.logs_button = QPushButton("打开日志目录")
        self.logs_button.clicked.connect(lambda: open_folder(self.root / "logs"))
        button_row.addWidget(self.logs_button)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh_status(self) -> None:
        self.status_label.setText(f"模型状态：{self.model_warmup.status_text}\n{tool_memory_summary(self.root)}")

    def prewarm_models(self) -> None:
        self.model_warmup.start()
        self.refresh_status()

    def release_models(self) -> None:
        self.model_warmup.release()
        self.refresh_status()

    def accept(self) -> None:
        self.settings.start_with_windows = self.startup_checkbox.isChecked()
        self.settings.auto_prewarm = True
        self.settings.idle_release_minutes = int(self.idle_release_combo.currentData())
        self.settings.rewrite_style = str(self.rewrite_style_combo.currentData())
        self.settings.asr_language = str(self.language_combo.currentData())
        if self.settings.start_with_windows:
            self.startup_registration.enable()
        else:
            self.startup_registration.disable()
        save_settings(self.root, self.settings)
        super().accept()


class RightAltKeyboardHook(QObject):
    activated = Signal()          # right Alt pressed
    ctrl_space = Signal()         # Ctrl+Space pressed
    ctrl_shift_space = Signal()   # Ctrl+Shift+Space pressed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hook_handle = None
        self._right_alt_down = False
        self._ctrl_down = False
        self._shift_down = False
        self._ctrl_space_down = False
        self._ctrl_shift_space_down = False
        self._callback = HOOK_CALLBACK(self._keyboard_proc)

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
                # Our own synthetic keystroke — pass through without processing
                return ctypes.windll.user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)
            if self._handle_key_event(int(event.vkCode), int(event.flags), int(w_param)):
                return 1  # suppress right Alt so it never reaches the target text field
        return ctypes.windll.user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

    def _handle_key_event(self, vk_code: int, flags: int, message: int) -> bool:
        # Re-sync _ctrl_down with hardware state each event to prevent stuck modifier.
        # GetAsyncKeyState returns bit 15 set if the key is physically held down.
        actual_ctrl = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

        # Track Ctrl key state (never suppress Ctrl itself)
        if vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
            if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._ctrl_down = True
            elif message in (WM_KEYUP, WM_SYSKEYUP):
                self._ctrl_down = False
            return False

        # Track Shift key state (never suppress Shift itself)
        if vk_code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._shift_down = True
            elif message in (WM_KEYUP, WM_SYSKEYUP):
                self._shift_down = False
            return False

        # If hardware says Ctrl is not held but our flag says it is, reset the flag.
        if self._ctrl_down and not actual_ctrl:
            self._ctrl_down = False
            self._ctrl_space_down = False
            self._ctrl_shift_space_down = False

        # Ctrl+Shift+Space / Ctrl+Space — handled here instead of RegisterHotKey so IME can't block it
        if vk_code == VK_SPACE:
            if self._ctrl_down and message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if self._shift_down:
                    if not self._ctrl_shift_space_down:
                        self._ctrl_shift_space_down = True
                        self.ctrl_shift_space.emit()
                else:
                    if not self._ctrl_space_down:
                        self._ctrl_space_down = True
                        self.ctrl_space.emit()
                return True  # suppress Space while Ctrl held
            if self._ctrl_space_down and message in (WM_KEYUP, WM_SYSKEYUP):
                self._ctrl_space_down = False
                return True  # suppress the matching key-up
            if self._ctrl_shift_space_down and message in (WM_KEYUP, WM_SYSKEYUP):
                self._ctrl_shift_space_down = False
                return True
            return False

        # Right Alt
        if not self._is_right_alt(vk_code, flags):
            return False
        if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if self._right_alt_down:
                return True  # suppress repeated key-down events too
            self._right_alt_down = True
            self.activated.emit()
            return True
        if message in (WM_KEYUP, WM_SYSKEYUP):
            was_down = self._right_alt_down
            self._right_alt_down = False
            return was_down  # suppress key-up only if we suppressed the key-down
        return False

    @staticmethod
    def _is_right_alt(vk_code: int, flags: int) -> bool:
        return vk_code == VK_RMENU or (vk_code == VK_MENU and bool(flags & LLKHF_EXTENDED))


class GlobalHotkeyReceiver(QWidget):
    activated = Signal()
    dictation_activated = Signal()
    rewrite_activated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._registered = False
        self._right_alt_hook = RightAltKeyboardHook(self)
        self._right_alt_hook.activated.connect(self.dictation_activated.emit)
        # Ctrl+Space is now handled in the low-level hook (bypasses IME interception)
        self._right_alt_hook.ctrl_space.connect(self.activated.emit)
        self._right_alt_hook.ctrl_shift_space.connect(self.rewrite_activated.emit)

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


class TextRewritePanel(QWidget):
    """Floating panel: paste text → AI rewrites → copy result. Independent of voice flow."""

    def __init__(self, model_warmup: DesktopModelWarmup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model_warmup = model_warmup
        self._thread: RewriteSelectionThread | None = None
        self.setWindowTitle("文字整理")
        self.setWindowIcon(QIcon())
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(440, 380)
        self.resize(480, 460)
        self.setStyleSheet(PANEL_STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        input_label = QLabel("粘贴要整理的文字：")
        layout.addWidget(input_label)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Ctrl+V 粘贴进来……")
        self.input_edit.setMinimumHeight(120)
        layout.addWidget(self.input_edit, stretch=1)

        self.rewrite_btn = QPushButton("AI 整理 ↓")
        self.rewrite_btn.setMinimumHeight(36)
        self.rewrite_btn.clicked.connect(self._start_rewrite)
        layout.addWidget(self.rewrite_btn)

        output_label = QLabel("整理结果：")
        layout.addWidget(output_label)

        self.output_edit = QPlainTextEdit()
        self.output_edit.setPlaceholderText("整理后的结果会出现在这里……")
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(120)
        layout.addWidget(self.output_edit, stretch=1)

        self.copy_btn = QPushButton("复制结果")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setMinimumHeight(36)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_result)
        layout.addWidget(self.copy_btn)

    def _start_rewrite(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if not self.model_warmup.is_ready:
            self.output_edit.setPlainText("模型尚未加载完成，请稍等后重试。")
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self.rewrite_btn.setEnabled(False)
        self.rewrite_btn.setText("整理中…")
        self.output_edit.clear()
        self.copy_btn.setEnabled(False)
        self._thread = RewriteSelectionThread(text, self.model_warmup)
        self._thread.completed.connect(self._on_completed)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_completed(self, result: str) -> None:
        self._thread = None
        self.output_edit.setPlainText(result)
        self.rewrite_btn.setEnabled(True)
        self.rewrite_btn.setText("AI 整理 ↓")
        self.copy_btn.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self._thread = None
        self.output_edit.setPlainText(f"整理失败：{message}")
        self.rewrite_btn.setEnabled(True)
        self.rewrite_btn.setText("AI 整理 ↓")

    def _copy_result(self) -> None:
        text = self.output_edit.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copy_btn.setText("已复制 ✓")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("复制结果"))

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

    def __init__(self, root: Path, model_warmup: DesktopModelWarmup | None = None) -> None:
        super().__init__()
        self.setObjectName("voicePromptWindow")
        self.setStyleSheet(PILL_STYLE)
        self.root = Path(root)
        self.recorder = PauseableAudioRecorder(self.root / "recordings")
        self.model_warmup = model_warmup or DesktopModelWarmup(self.root)
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
        if self._pill_state == self._STATE_MODEL_LOADING:
            self.pill_label.setText(f"模型加载中{'.' * (self._anim_frame + 1)}")
        elif self._pill_state == self._STATE_RECORDING:
            mode = "AI模式" if self.recording_mode == "ai" else "听写"
            self.pill_label.setText(f"{mode}（录音中）{dots}")
        elif self._pill_state == self._STATE_ASR:
            self.pill_label.setText(f"识别中{'.' * (self._anim_frame + 1)}")
        elif self._pill_state == self._STATE_PROCESSING:
            self.pill_label.setText(f"处理中{'.' * (self._anim_frame + 1)}")
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
        mode_text = "AI模式" if self.recording_mode == "ai" else "听写"
        self._show_pill(f"{mode_text}（录音中）•")
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
        self._show_pill("模型加载中.")
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
        )
        self._last_model_state = "unknown"
        self.rewrite_panel = TextRewritePanel(self.window.model_warmup)
        self.rewrite_panel.setWindowIcon(app_icon_for_root(self.root))
        self.tray = QSystemTrayIcon(app_icon_for_root(self.root), app)
        self.tray.setToolTip("Voice Prompt Tool")
        self.hotkey = GlobalHotkeyReceiver() if enable_hotkey and os.name == "nt" else None
        self._build_tray_menu()
        if self.hotkey is not None:
            self.hotkey.activated.connect(lambda: self.handle_recording_hotkey(mode="ai"))
            self.hotkey.dictation_activated.connect(lambda: self.handle_recording_hotkey(mode="dictation"))
            self.hotkey.rewrite_activated.connect(self.open_rewrite_panel)
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

    def _build_tray_menu(self) -> None:
        menu = QMenu()
        start_action = QAction("开始录音并整理", menu)
        start_action.triggered.connect(lambda: self.handle_recording_hotkey(mode="ai"))
        menu.addAction(start_action)
        dictation_action = QAction("快速听写", menu)
        dictation_action.triggered.connect(lambda: self.handle_recording_hotkey(mode="dictation"))
        menu.addAction(dictation_action)
        rewrite_action = QAction("整理文字...", menu)
        rewrite_action.triggered.connect(self.open_rewrite_panel)
        menu.addAction(rewrite_action)
        settings_action = QAction("设置", menu)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        prewarm_action = QAction("预热模型", menu)
        prewarm_action.triggered.connect(lambda: self.start_model_warmup(show_window=True))
        menu.addAction(prewarm_action)
        release_action = QAction("释放模型", menu)
        release_action.triggered.connect(self.release_models_with_notice)
        menu.addAction(release_action)
        logs_action = QAction("打开日志目录", menu)
        logs_action.triggered.connect(lambda: open_folder(self.root / "logs"))
        menu.addAction(logs_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

    def open_settings(self) -> None:
        previous_rewrite_style = self.settings.rewrite_style
        previous_asr_language = self.settings.asr_language
        dialog = SettingsDialog(
            root=self.root,
            settings=self.settings,
            model_warmup=self.window.model_warmup,
            startup_registration=self.startup_registration,
            parent=None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.settings.rewrite_style != previous_rewrite_style or self.settings.asr_language != previous_asr_language:
            self.window.model_warmup.release()
        if not self.window.model_warmup.is_ready:
            self.start_model_warmup(show_window=True)

    def handle_recording_hotkey(self, mode: str = "ai") -> None:
        if not self.window.is_model_ready:
            self.start_model_warmup(show_window=True)
            self.tray.showMessage(
                "模型正在加载",
                "加载完成后才能开始录音。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        self.window.handle_recording_hotkey(mode=mode)

    def start_model_warmup(self, show_window: bool = True) -> None:
        self.window.model_warmup.start()
        self._last_model_state = "warming"
        self.tray.setToolTip("Voice Prompt Tool - 模型加载中")
        self.window.show_model_loading_status()

    def release_models_with_notice(self) -> None:
        self.window.model_warmup.release()
        self._last_model_state = "released"
        self.tray.setToolTip("Voice Prompt Tool - 模型已释放")
        self.tray.showMessage(
            "模型已释放",
            "如需继续使用，请先预热模型；热键会先进入加载状态。",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _refresh_model_status(self) -> None:
        if self.window.model_warmup.is_ready:
            if self._last_model_state == "warming":
                self.window.show_model_ready_status()
                self.tray.showMessage(
                    "模型已加载完成",
                    "现在可以使用 Ctrl+Space、右 Alt、或 Ctrl+Shift+Space 整理选中文字。",
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
            self._last_model_state = "ready"
            self.tray.setToolTip("Voice Prompt Tool - 模型已就绪")
            return
        if self.window.model_warmup.is_warming:
            self._last_model_state = "warming"
            self.tray.setToolTip("Voice Prompt Tool - 模型加载中")
            return
        if self._last_model_state != "released":
            self.tray.setToolTip("Voice Prompt Tool - 模型未加载")

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
