from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable, Sequence


class OllamaServiceManager:
    def __init__(
        self,
        root: Path,
        endpoint: str = "http://127.0.0.1:11434",
        health_check: Callable[[], bool] | None = None,
        command_runner: Callable[[Sequence[str]], object] | None = None,
    ) -> None:
        self.root = Path(root)
        self.endpoint = endpoint.rstrip("/")
        self._health_check = health_check or self._default_health_check
        self._command_runner = command_runner or self._default_command_runner
        self._started_by_self = False

    @property
    def started_by_self(self) -> bool:
        return self._started_by_self

    def start_if_needed(self) -> None:
        if self._health_check():
            self._started_by_self = False
            return

        self._command_runner(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.root / "start-ollama.ps1"),
                "-Quiet",
            ]
        )
        self._started_by_self = True

    def stop_if_started(self) -> None:
        if not self._started_by_self:
            return

        self.stop_local_processes()
        self._started_by_self = False

    def stop_local_processes(self) -> None:
        self._command_runner(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.root / "stop-ollama.ps1"),
                "-Quiet",
            ]
        )

    def _default_health_check(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=2) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    @staticmethod
    def _default_command_runner(command: Sequence[str]) -> None:
        kwargs = {}
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(list(command), check=True, **kwargs)
