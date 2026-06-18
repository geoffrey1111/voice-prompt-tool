from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


VALID_REWRITE_STYLES = ("faithful", "concise", "semantic")
VALID_IDLE_RELEASE_MINUTES = (0, 10, 30, 60)
VALID_ASR_LANGUAGES = ("zh", "en")


@dataclass
class DesktopSettings:
    auto_prewarm: bool = True
    idle_release_minutes: int = 0
    rewrite_style: str = "semantic"
    start_with_windows: bool = False
    asr_language: str = "zh"
    hotkey_ai: str = "ctrl+space"
    hotkey_dictation: str = "right_alt"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesktopSettings":
        settings = cls()
        settings.auto_prewarm = bool(data.get("auto_prewarm", settings.auto_prewarm))
        settings.idle_release_minutes = _valid_idle_release_minutes(data.get("idle_release_minutes"))
        settings.rewrite_style = _valid_rewrite_style(data.get("rewrite_style"))
        settings.start_with_windows = bool(data.get("start_with_windows", settings.start_with_windows))
        settings.asr_language = _valid_asr_language(data.get("asr_language"))
        settings.hotkey_ai = _valid_hotkey(data.get("hotkey_ai"), "ctrl+space")
        settings.hotkey_dictation = _valid_hotkey(data.get("hotkey_dictation"), "right_alt")
        return settings


def settings_path(root: Path) -> Path:
    return Path(root) / "settings.json"


def load_settings(root: Path) -> DesktopSettings:
    path = settings_path(root)
    if not path.exists():
        return DesktopSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DesktopSettings()
    if not isinstance(data, dict):
        return DesktopSettings()
    return DesktopSettings.from_dict(data)


def save_settings(root: Path, settings: DesktopSettings) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    settings_path(root).write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class StartupRegistration:
    def __init__(self, root: Path, startup_dir: Path | None = None) -> None:
        self.root = Path(root)
        self.startup_dir = startup_dir or _default_startup_dir()
        self.shortcut_path = self.startup_dir / "Voice Prompt Tool.bat"

    def is_enabled(self) -> bool:
        return self.shortcut_path.exists()

    def enable(self) -> None:
        desktop_script = self.root / "desktop.ps1"
        if not desktop_script.exists():
            raise FileNotFoundError(desktop_script)
        self.startup_dir.mkdir(parents=True, exist_ok=True)
        self.shortcut_path.write_text(
            "@echo off\r\n"
            f'start "" powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{desktop_script}" --start-hidden\r\n',
            encoding="utf-8",
        )

    def disable(self) -> None:
        if self.shortcut_path.exists():
            self.shortcut_path.unlink()


def _default_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; cannot locate Windows Startup folder.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


_HOTKEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789+_")


def _valid_hotkey(value: Any, default: str) -> str:
    if isinstance(value, str) and value and all(c in _HOTKEY_CHARS for c in value):
        return value
    return default


def _valid_rewrite_style(value: Any) -> str:
    if isinstance(value, str) and value in VALID_REWRITE_STYLES:
        return value
    return "semantic"


def _valid_asr_language(value: Any) -> str:
    if isinstance(value, str) and value in VALID_ASR_LANGUAGES:
        return value
    return "zh"


def _valid_idle_release_minutes(value: Any) -> int:
    try:
        minutes = int(value)
    except Exception:
        return 0
    if minutes in VALID_IDLE_RELEASE_MINUTES:
        return minutes
    return 0
