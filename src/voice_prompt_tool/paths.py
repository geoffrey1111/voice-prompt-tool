from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ROOT = Path(os.environ.get("VOICE_PROMPT_ROOT", r"D:\desktop\临时处理\voice_prompt_tool"))


def configure_cache_environment(root: Path = DEFAULT_ROOT) -> None:
    cache_root = Path(root) / "cache"
    os.environ["HF_HOME"] = str(cache_root / "huggingface")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_root / "huggingface" / "hub")
    os.environ["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    os.environ["PIP_CACHE_DIR"] = str(cache_root / "pip")


def ensure_runtime_dirs(root: Path = DEFAULT_ROOT) -> None:
    root_path = Path(root)
    for folder in (
        root_path,
        root_path / "cache",
        root_path / "cache" / "huggingface",
        root_path / "cache" / "huggingface" / "hub",
        root_path / "cache" / "pip",
        root_path / "cache" / "uv",
        root_path / "cache" / "xdg",
        root_path / "recordings",
    ):
        folder.mkdir(parents=True, exist_ok=True)
