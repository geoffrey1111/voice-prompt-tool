from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time
from dataclasses import dataclass

from voice_prompt_tool.clipboard import copy_text


VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_LEFT = 0x25
VK_END = 0x23
VK_V = 0x56
VK_BACK = 0x08
KEYEVENTF_KEYUP = 0x0002

_WM_GETTEXTLENGTH = 0x000E
_EM_SETSEL = 0x00B1
_EM_REPLACESEL = 0x00C2

# Debug log: set VOICE_TOOL_INJECT_DEBUG=1 to enable
_DEBUG = os.environ.get("VOICE_TOOL_INJECT_DEBUG") == "1"
_DEBUG_LOG = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "voice_tool_inject_debug.log")


def _dbg(msg: str) -> None:
    if not _DEBUG:
        return
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} {msg}\n")
    except Exception:
        pass


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def ai_placeholder_text(text: str) -> str:
    return f"{text}（处理前，整理中）"


@dataclass
class DictationSession:
    target_hwnd: int | None
    inserted_text: str = ""
    inserted_at_input_tick: int = 0
    # Mouse cursor position (screen coords) captured when recording started.
    # Used to re-click the text input widget for Qt-based apps after focus is restored.
    cursor_x: int = 0
    cursor_y: int = 0


class WindowsInputBackend:
    def get_foreground_window(self) -> int | None:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None

    def is_window(self, hwnd: int | None) -> bool:
        return bool(hwnd and ctypes.windll.user32.IsWindow(hwnd))

    def set_foreground_window(self, hwnd: int | None) -> bool:
        if not hwnd:
            return False
        return bool(ctypes.windll.user32.SetForegroundWindow(hwnd))

    def force_foreground_window(self, hwnd: int | None) -> bool:
        """Set hwnd as foreground, bypassing the Windows foreground-lock timeout."""
        if not hwnd:
            return False
        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return True
        fg = ctypes.windll.user32.GetForegroundWindow()
        fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(fg, None) if fg else 0
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = bool(fg_tid and fg_tid != cur_tid)
        if attached:
            ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        if attached:
            ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
        result = ctypes.windll.user32.GetForegroundWindow() == hwnd
        _dbg(f"force_foreground_window({hwnd}): fg_before={fg}, result={result}, fg_after={ctypes.windll.user32.GetForegroundWindow()}")
        return result

    def get_last_input_tick(self) -> int:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0
        return int(info.dwTime)

    def copy_text(self, text: str) -> None:
        copy_text(text)

    def paste_text(self, text: str) -> None:
        self.copy_text(text)
        _press_ctrl_v()

    def _get_focused_control(self, target_hwnd: int) -> int:
        """Return the HWND with keyboard focus in target_hwnd's thread (0 on failure)."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
        cur_tid = kernel32.GetCurrentThreadId()
        if target_tid and target_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, target_tid, True)
            focused = user32.GetFocus()
            user32.AttachThreadInput(cur_tid, target_tid, False)
        else:
            focused = user32.GetFocus()
        return int(focused) if focused else 0

    def get_window_class(self, hwnd: int | None) -> str:
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(128)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 128)
        return buf.value

    def post_click_to_restore_focus(self, hwnd: int, screen_x: int, screen_y: int) -> None:
        """Send WM_LBUTTONDOWN/UP at (screen_x, screen_y) to give Qt text widgets focus.

        Qt apps use a single Win32 HWND; internal widget focus is restored only when
        the window receives a real (or simulated) click. This is needed because
        SetForegroundWindow alone doesn't restore Qt widget focus reliably.
        """
        # Clamp y coordinate to stay well above the toolbar row at the window bottom.
        # WeChat's toolbar is ~55px from the bottom; the text input ends ~80px from bottom.
        # Clicking closer than 90px to the bottom risks hitting toolbar buttons
        # (e.g. the microphone toggle which switches WeChat to voice-input mode).
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        max_safe_y = rect.bottom - 90
        if screen_y > max_safe_y:
            screen_y = rect.bottom - 160  # upper portion of the text input area
            screen_x = (rect.left + rect.right) // 2
        pt = ctypes.wintypes.POINT(screen_x, screen_y)
        ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
        lparam = (pt.y << 16) | (pt.x & 0xFFFF)
        _dbg(f"post_click_to_restore_focus: hwnd={hwnd} screen=({screen_x},{screen_y}) client=({pt.x},{pt.y})")
        ctypes.windll.user32.PostMessageW(hwnd, 0x0201, 1, lparam)  # WM_LBUTTONDOWN
        ctypes.windll.user32.PostMessageW(hwnd, 0x0202, 0, lparam)  # WM_LBUTTONUP

    _EDIT_CLASSES = frozenset({
        "Edit", "RichEdit20W", "RichEdit20A",
        "RichEditD2DPT", "RICHEDIT50W", "RICHEDIT50A",
    })

    def _find_edit_children(self, hwnd: int) -> list[int]:
        """Enumerate child windows that are standard Win32/RichEdit text controls."""
        results: list[int] = []
        cb_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        def _cb(child: int, _: int) -> bool:
            cls_buf = ctypes.create_unicode_buffer(64)
            ctypes.windll.user32.GetClassNameW(child, cls_buf, 64)
            if cls_buf.value in WindowsInputBackend._EDIT_CLASSES:
                results.append(int(child))
            return True

        ctypes.windll.user32.EnumChildWindows(hwnd, cb_type(_cb), 0)
        return results

    def _em_replace(self, ctrl_hwnd: int, old_length: int, text: str) -> bool:
        """Replace old_length chars before cursor via EM_SETSEL + EM_REPLACESEL.

        Works for any standard Win32/RichEdit control without needing focus.
        Verifies success by comparing text-length before and after.
        """
        try:
            user32 = ctypes.windll.user32
            len_before = user32.SendMessageW(ctrl_hwnd, _WM_GETTEXTLENGTH, 0, 0)
            _dbg(f"  _em_replace ctrl={ctrl_hwnd}: len_before={len_before}, old_length={old_length}")
            if len_before <= 0 or len_before < old_length:
                return False
            start = len_before - old_length
            user32.SendMessageW(ctrl_hwnd, _EM_SETSEL, start, len_before)
            buf = ctypes.create_unicode_buffer(text)
            user32.SendMessageW(ctrl_hwnd, _EM_REPLACESEL, 1, buf)
            # Verify: new length should equal len_before - old_length + len(text)
            # Allow ±2 for \r\n / line-ending differences.
            len_after = user32.SendMessageW(ctrl_hwnd, _WM_GETTEXTLENGTH, 0, 0)
            expected = len_before - old_length + len(text)
            ok = abs(len_after - expected) <= 2
            _dbg(f"    len_after={len_after}, expected={expected}, ok={ok}")
            return ok
        except Exception as exc:
            _dbg(f"  _em_replace exception: {exc}")
            return False

    def try_em_replace(self, target_hwnd: int, old_length: int, text: str) -> bool:
        """Try EM replacement; searches focused child then edit-class children then main window.

        Returns True only after verifying the replacement length matches.
        """
        focused = self._get_focused_control(target_hwnd)
        _dbg(f"try_em_replace: target={target_hwnd}, focused={focused}, old_length={old_length}")

        seen: set[int] = set()
        candidates: list[int] = []
        # Deliberately exclude target_hwnd itself: WM_GETTEXTLENGTH on a non-Edit top-level
        # window returns the window-title length, which can accidentally satisfy the length
        # check for short ASR texts and cause a false-positive (silent no-op "replacement").
        for hwnd in [focused, *self._find_edit_children(target_hwnd)]:
            if hwnd and hwnd != target_hwnd and hwnd not in seen:
                candidates.append(hwnd)
                seen.add(hwnd)

        for ctrl in candidates:
            if self._em_replace(ctrl, old_length, text):
                _dbg(f"  EM succeeded on ctrl={ctrl}")
                return True
        _dbg("  EM failed on all candidates; falling back to keyboard")
        return False

    def kbd_replace(self, old_length: int, text: str) -> None:
        """Replace old_length chars before cursor using keyboard simulation."""
        _dbg(f"kbd_replace: old_length={old_length}, fg={ctypes.windll.user32.GetForegroundWindow()}")
        # Set clipboard BEFORE making the selection. In Qt apps, clipboard-change
        # messages (WM_CHANGECBCHAIN) can interrupt an in-progress Shift+Left selection,
        # causing the paste to overwrite nothing instead of the selected text.
        self.copy_text(text)
        _dbg(f"  after copy: fg={ctypes.windll.user32.GetForegroundWindow()}")
        _select_previous_chars(old_length)
        _dbg(f"  after select: fg={ctypes.windll.user32.GetForegroundWindow()}")
        _press_ctrl_v()
        _dbg(f"  after ctrl+v: fg={ctypes.windll.user32.GetForegroundWindow()}")

    def replace_previous_text(self, old_length: int, text: str) -> None:
        """Legacy: select old_length chars before cursor then paste text (keyboard only)."""
        _select_previous_chars(old_length)
        self.copy_text(text)
        _press_ctrl_v()


class TextInjector:
    def __init__(self, backend: WindowsInputBackend | None = None) -> None:
        self.backend = backend or WindowsInputBackend()

    def capture_target(self, excluded_hwnd: int | None = None) -> DictationSession:
        hwnd = self.backend.get_foreground_window()
        if hwnd == excluded_hwnd:
            hwnd = None
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return DictationSession(target_hwnd=hwnd, cursor_x=pt.x, cursor_y=pt.y)

    def insert_text(self, session: DictationSession | None, text: str) -> bool:
        if session is None or not text:
            return False
        if not self.backend.is_window(session.target_hwnd):
            return False
        if not self.backend.force_foreground_window(session.target_hwnd):
            _dbg(f"insert_text: force_foreground_window failed for {session.target_hwnd}")
            return False
        time.sleep(0.10)

        target_cls = self.backend.get_window_class(session.target_hwnd)
        _dbg(f"insert_text: target={session.target_hwnd} class={target_cls!r} cursor=({session.cursor_x},{session.cursor_y})")
        if target_cls.startswith("Qt5") and session.cursor_x and session.cursor_y:
            self.backend.post_click_to_restore_focus(
                session.target_hwnd, session.cursor_x, session.cursor_y
            )
            time.sleep(0.20)  # increased: give Qt more time to restore widget focus

        # Sample text length before paste so we can verify the paste landed.
        pre_length = self._sample_edit_lengths(session.target_hwnd)
        _dbg(f"insert_text: pre_length={pre_length}, fg={ctypes.windll.user32.GetForegroundWindow()}")

        self.backend.paste_text(text)
        time.sleep(0.12)  # let target window process the paste

        # Verify paste landed when Win32/RichEdit controls are accessible.
        # For Qt-only apps (e.g. WeChat) _sample_edit_lengths returns -1; we skip
        # verification and trust the timing, but still don't mark session.inserted_text
        # until we're as confident as possible.
        if pre_length >= 0:
            post_length = self._sample_edit_lengths(session.target_hwnd)
            expected = pre_length + len(text)
            _dbg(f"insert_text: post_length={post_length}, expected≈{expected}")
            if abs(post_length - expected) > max(3, len(text) // 3):
                _dbg("insert_text: verification FAILED — text did not land, will retry")
                return False  # don't set inserted_text; caller will retry

        session.inserted_text = text
        session.inserted_at_input_tick = self.backend.get_last_input_tick()
        return True

    def _sample_edit_lengths(self, hwnd: int) -> int:
        """Total text length across accessible Win32/RichEdit children. -1 if none found.

        Only counts controls whose class is in WindowsInputBackend._EDIT_CLASSES so that
        Qt top-level HWNDs (which return window-title length from WM_GETTEXTLENGTH) don't
        pollute the measurement.
        """
        focused = self.backend._get_focused_control(hwnd)
        children = self.backend._find_edit_children(hwnd)
        seen: set[int] = set()
        total = 0
        found = False

        # Only include focused control if it's a known Edit class
        candidates: list[int] = list(children)
        if focused and focused not in seen:
            cls_buf = ctypes.create_unicode_buffer(64)
            ctypes.windll.user32.GetClassNameW(focused, cls_buf, 64)
            if cls_buf.value in WindowsInputBackend._EDIT_CLASSES:
                candidates.insert(0, focused)

        for ctrl in candidates:
            if not ctrl or ctrl in seen:
                continue
            seen.add(ctrl)
            try:
                n = ctypes.windll.user32.SendMessageW(ctrl, _WM_GETTEXTLENGTH, 0, 0)
                if n >= 0:
                    total += n
                    found = True
            except Exception:
                pass
        return total if found else -1

    def replace_inserted_text(self, session: DictationSession | None, text: str) -> bool:
        if session is None or not session.inserted_text or not text:
            self._copy_fallback(text)
            return False
        if not self.backend.is_window(session.target_hwnd):
            self._copy_fallback(text)
            return False

        old_length = len(session.inserted_text)
        target_hwnd = session.target_hwnd

        _dbg(f"replace_inserted_text: target={target_hwnd}, old_length={old_length}, fg={ctypes.windll.user32.GetForegroundWindow()}")

        # Always use keyboard simulation so the user sees the visual selection animation
        # (Shift+Left × n highlights the ASR text, then Ctrl+V replaces it).
        # EM_SETSEL/EM_REPLACESEL is deliberately skipped as the primary path because it
        # replaces silently with no visual feedback. It is kept only as a last-resort
        # fallback after keyboard simulation fails.
        if not self.backend.force_foreground_window(target_hwnd):
            _dbg("  force_foreground_window failed; trying EM fallback then clipboard")
            if self.backend.try_em_replace(target_hwnd, old_length, text):
                session.inserted_text = text
                return True
            self._copy_fallback(text)
            return False
        time.sleep(0.10)

        # For Qt-based apps, restore widget focus via a safe geometry-based click,
        # then use Ctrl+End to ensure the caret is at the end of the text before
        # Shift+Left selection. We derive the click position from the window rect
        # rather than the captured cursor position (which may have moved).
        target_cls = self.backend.get_window_class(target_hwnd)
        if target_cls.startswith("Qt5"):
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
            safe_x = (rect.left + rect.right) // 2
            safe_y = rect.bottom - 160  # upper portion of text input, well above toolbar
            self.backend.post_click_to_restore_focus(target_hwnd, safe_x, safe_y)
            time.sleep(0.15)
            # Move caret to end so Shift+Left selects exactly the placeholder.
            _key_down(VK_CONTROL); _tap(VK_END); _key_up(VK_CONTROL)
            time.sleep(0.08)

        self.backend.kbd_replace(old_length, text)
        session.inserted_text = text
        return True

    def _copy_fallback(self, text: str) -> None:
        if text:
            copy_method = getattr(self.backend, "copy_text", None)
            if callable(copy_method):
                copy_method(text)
            else:
                copy_text(text)


def _key_down(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _tap(vk: int) -> None:
    _key_down(vk)
    _key_up(vk)


def _press_ctrl_v() -> None:
    _key_down(VK_CONTROL)
    _tap(VK_V)
    _key_up(VK_CONTROL)


def _select_previous_chars(count: int) -> None:
    if count <= 0:
        return
    _key_down(VK_SHIFT)
    try:
        for _ in range(count):
            _tap(VK_LEFT)
    finally:
        _key_up(VK_SHIFT)
