from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from voice_prompt_tool.cli import build_corrector, build_rewriter, build_transcriber
from voice_prompt_tool.desktop_ollama import OllamaServiceManager
from voice_prompt_tool.paths import configure_cache_environment, ensure_runtime_dirs
from voice_prompt_tool.pipeline import VoicePromptPipeline, VoicePromptResult


def build_desktop_pipeline(
    root: Path,
    ollama_model: str = "qwen3:4b-instruct",
    asr_backend: str = "sensevoice",
    asr_device: str = "cpu",
    asr_compute_type: str = "int8",
    use_ollama: bool = True,
    use_ollama_corrector: bool = False,
    ollama_keep_alive: int | str = "10m",
) -> VoicePromptPipeline:
    args = argparse.Namespace(
        asr_backend=asr_backend,
        asr_device=asr_device,
        asr_compute_type=asr_compute_type,
        whisper_model="large-v3",
    )
    transcriber = build_transcriber(args, Path(root))
    return VoicePromptPipeline(
        transcribe=transcriber.transcribe,
        correct_transcript=build_corrector(
            ollama_model,
            use_ollama=use_ollama_corrector and use_ollama,
        ),
        rewrite=build_rewriter(ollama_model, use_ollama=use_ollama, keep_alive=ollama_keep_alive),
    )


def process_recording_with_local_models(
    audio_path: Path,
    root: Path,
    ollama_manager: OllamaServiceManager | None = None,
) -> VoicePromptResult:
    return process_recording_in_stages(audio_path=audio_path, root=root, ollama_manager=ollama_manager)


def process_recording_transcript_only(
    audio_path: Path,
    root: Path,
    transcribe: Callable[[Path], str] | None = None,
    correct_transcript: Callable[[str], str] | None = None,
) -> VoicePromptResult:
    root = Path(root)
    configure_cache_environment(root)
    ensure_runtime_dirs(root)

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    if transcribe is None:
        args = argparse.Namespace(
            asr_backend="sensevoice",
            asr_device="cpu",
            asr_compute_type="int8",
            whisper_model="large-v3",
        )
        transcriber = build_transcriber(args, root)
        transcribe = transcriber.transcribe
    correct_transcript = correct_transcript or build_corrector("qwen3:4b-instruct", use_ollama=False)

    raw_text = transcribe(audio_path).strip()
    if not raw_text:
        raise ValueError("没有识别到有效语音内容，请靠近麦克风重新录制。")
    corrected_text = correct_transcript(raw_text).strip()
    if not corrected_text:
        raise ValueError("转写校对后为空，请重新录制。")
    return VoicePromptResult(raw_text=raw_text, corrected_text=corrected_text, optimized_prompt=corrected_text)


def process_recording_in_stages(
    audio_path: Path,
    root: Path,
    transcribe: Callable[[Path], str] | None = None,
    correct_transcript: Callable[[str], str] | None = None,
    rewrite: Callable[[str], str] | None = None,
    ollama_manager: OllamaServiceManager | None = None,
    on_transcript: Callable[[VoicePromptResult], None] | None = None,
    stop_ollama_after: bool = True,
) -> VoicePromptResult:
    root = Path(root)
    configure_cache_environment(root)
    ensure_runtime_dirs(root)

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    if transcribe is None or correct_transcript is None or rewrite is None:
        args = argparse.Namespace(
            asr_backend="sensevoice",
            asr_device="cpu",
            asr_compute_type="int8",
            whisper_model="large-v3",
        )
        transcriber = build_transcriber(args, root)
        transcribe = transcribe or transcriber.transcribe
        correct_transcript = correct_transcript or build_corrector("qwen3:4b-instruct", use_ollama=False)
        rewrite = rewrite or build_rewriter("qwen3:4b-instruct", use_ollama=True)

    raw_text = transcribe(audio_path).strip()
    if not raw_text:
        raise ValueError("没有识别到有效语音内容，请靠近麦克风重新录制。")

    corrected_text = correct_transcript(raw_text).strip()
    if not corrected_text:
        raise ValueError("转写校对后为空，请重新录制。")

    if on_transcript is not None:
        on_transcript(
            VoicePromptResult(
                raw_text=raw_text,
                corrected_text=corrected_text,
                optimized_prompt="",
            )
        )

    manager = ollama_manager or OllamaServiceManager(root)
    manager.start_if_needed()
    try:
        optimized_prompt = rewrite(corrected_text).strip()
    finally:
        if stop_ollama_after:
            manager.stop_if_started()

    return VoicePromptResult(
        raw_text=raw_text,
        corrected_text=corrected_text,
        optimized_prompt=optimized_prompt,
    )
