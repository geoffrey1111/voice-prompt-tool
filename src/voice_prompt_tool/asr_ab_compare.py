from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from voice_prompt_tool.cli import build_transcriber
from voice_prompt_tool.paths import DEFAULT_ROOT, configure_cache_environment, ensure_runtime_dirs


@dataclass(frozen=True)
class AsrRunResult:
    name: str
    seconds: float
    text: str


def format_ab_report(audio_path: str, sensevoice: AsrRunResult, qwen: AsrRunResult) -> str:
    return (
        f"音频：{audio_path}\n\n"
        f"===== {sensevoice.name} ({sensevoice.seconds:.2f}s) =====\n"
        f"{sensevoice.text}\n\n"
        f"===== {qwen.name} ({qwen.seconds:.2f}s) =====\n"
        f"{qwen.text}\n"
    )


def timed_run(name: str, func: Callable[[], str]) -> AsrRunResult:
    started_at = time.perf_counter()
    text = func().strip()
    return AsrRunResult(name=name, seconds=time.perf_counter() - started_at, text=text)


def transcribe_with_sensevoice(audio_path: Path, root: Path, device: str = "cpu") -> str:
    args = argparse.Namespace(
        asr_backend="sensevoice",
        asr_device=device,
        asr_compute_type="int8",
        whisper_model="large-v3",
    )
    transcriber = build_transcriber(args, root)
    return transcriber.transcribe(audio_path)


def transcribe_with_qwen_subprocess(
    audio_path: Path,
    root: Path,
    qwen_python: Path,
    model_name: str,
    device: str,
    language: str,
) -> str:
    script = Path(root) / "scripts" / "qwen3_asr_transcribe.py"
    if not script.exists():
        raise FileNotFoundError(script)
    if not qwen_python.exists():
        raise FileNotFoundError(f"Qwen3-ASR python not found: {qwen_python}")

    env = os.environ.copy()
    env["VOICE_PROMPT_ROOT"] = str(root)
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [
            str(qwen_python),
            str(script),
            "--audio",
            str(audio_path),
            "--root",
            str(root),
            "--model",
            model_name,
            "--device",
            device,
            "--language",
            language,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=900,
    )
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare SenseVoiceSmall and Qwen3-ASR on the same audio file.")
    parser.add_argument("--audio", required=True, help="WAV/audio file to transcribe.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Project root.")
    parser.add_argument("--sensevoice-device", default="cpu")
    parser.add_argument("--qwen-python", default="")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-ASR-0.6B")
    parser.add_argument("--qwen-device", default="cpu")
    parser.add_argument("--qwen-language", default="Chinese")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    audio_path = Path(args.audio)
    qwen_python = Path(args.qwen_python) if args.qwen_python else root / ".qwen3-asr-venv" / "Scripts" / "python.exe"

    configure_cache_environment(root)
    ensure_runtime_dirs(root)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    sensevoice = timed_run(
        "SenseVoiceSmall",
        lambda: transcribe_with_sensevoice(audio_path, root, device=args.sensevoice_device),
    )
    qwen = timed_run(
        args.qwen_model,
        lambda: transcribe_with_qwen_subprocess(
            audio_path=audio_path,
            root=root,
            qwen_python=qwen_python,
            model_name=args.qwen_model,
            device=args.qwen_device,
            language=args.qwen_language,
        ),
    )
    print(format_ab_report(str(audio_path), sensevoice, qwen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
