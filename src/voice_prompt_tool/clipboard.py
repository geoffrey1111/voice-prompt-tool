from __future__ import annotations

import subprocess


def copy_text(text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
        return
    except Exception:
        pass

    subprocess.run(["clip"], input=text, text=True, check=True)

