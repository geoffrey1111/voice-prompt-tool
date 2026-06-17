from __future__ import annotations

import argparse
import os
from pathlib import Path

from voice_prompt_tool.asr import FasterWhisperTranscriber
from voice_prompt_tool.clipboard import copy_text
from voice_prompt_tool.ollama_rewriter import OllamaPromptRewriter, OllamaUnavailable
from voice_prompt_tool.ollama_transcript_corrector import OllamaTranscriptCorrector
from voice_prompt_tool.paths import DEFAULT_ROOT, configure_cache_environment, ensure_runtime_dirs
from voice_prompt_tool.pipeline import VoicePromptPipeline, VoicePromptResult
from voice_prompt_tool.recorder import record_until_enter
from voice_prompt_tool.rewrite_guard import guard_rewrite_result
from voice_prompt_tool.sensevoice_asr import SenseVoiceTranscriber
from voice_prompt_tool.text_polisher import polish_spoken_text
from voice_prompt_tool.transcript_corrector import correct_transcript


def format_result(result: VoicePromptResult) -> str:
    corrected_section = ""
    if result.corrected_text and result.corrected_text != result.raw_text:
        corrected_section = (
            "\n"
            "================ 校对后文本 ================\n"
            f"{result.corrected_text}\n"
        )
    return (
        "\n"
        "================ 原始识别文本 ================\n"
        f"{result.raw_text}\n\n"
        f"{corrected_section}\n"
        "================ 整理后的口述文本 ================\n"
        f"{result.optimized_prompt}\n"
        "=====================================================\n"
    )


def build_rewriter(model: str, use_ollama: bool, keep_alive: int | str = 0, rewrite_style: str = "semantic"):
    if not use_ollama:
        return polish_spoken_text

    rewriter_kwargs = {}
    if keep_alive != 0:
        rewriter_kwargs["keep_alive"] = keep_alive
    if rewrite_style != "concise":
        rewriter_kwargs["rewrite_style"] = rewrite_style
    ollama = OllamaPromptRewriter(model=model, **rewriter_kwargs)

    def rewrite_with_fallback(text: str) -> str:
        try:
            return guard_rewrite_result(text, ollama.rewrite(text))
        except OllamaUnavailable as exc:
            print(f"本地 Ollama/Qwen 语义重组暂不可用，使用规则整理。原因：{exc}")
            return polish_spoken_text(text)

    return rewrite_with_fallback


def build_corrector(model: str, use_ollama: bool):
    if not use_ollama:
        return correct_transcript

    ollama = OllamaTranscriptCorrector(model=model)

    def correct_with_fallback(text: str) -> str:
        try:
            return ollama.correct(text)
        except OllamaUnavailable as exc:
            print(f"本地 Ollama/Qwen 转写校对暂不可用，使用规则校对。原因：{exc}")
            return correct_transcript(text)

    return correct_with_fallback


def build_transcriber(args: argparse.Namespace, root: Path):
    if args.asr_backend == "sensevoice":
        model_dir = Path(
            os.environ.get(
                "VOICE_PROMPT_SENSEVOICE_MODEL_DIR",
                str(root / "cache" / "hf-models" / "SenseVoiceSmall"),
            )
        )
        recordings_ascii_dir = os.environ.get("VOICE_PROMPT_RECORDINGS_ASCII")
        return SenseVoiceTranscriber(
            model_dir=model_dir,
            device=args.asr_device,
            recordings_dir=root / "recordings",
            recordings_ascii_dir=Path(recordings_ascii_dir) if recordings_ascii_dir else None,
        )

    return FasterWhisperTranscriber(
        model_size=args.whisper_model,
        cache_dir=root / "cache" / "faster-whisper",
        device=args.asr_device,
        compute_type=args.asr_compute_type,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local voice-to-AI-prompt prototype.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Project runtime root.")
    parser.add_argument("--asr-backend", default="sensevoice", choices=["sensevoice", "whisper"], help="Speech recognition backend.")
    parser.add_argument("--whisper-model", default="large-v3", help="faster-whisper model size, e.g. small/large-v3.")
    parser.add_argument("--asr-device", default="cpu", help="ASR device, e.g. cpu, cuda, or cuda:0.")
    parser.add_argument("--asr-compute-type", default="int8", help="Whisper compute type, e.g. int8 or float16.")
    parser.add_argument("--ollama-model", default="qwen3:4b-instruct", help="Ollama model name for prompt rewriting.")
    parser.add_argument("--use-ollama-corrector", action="store_true", help="Use local Ollama/Qwen for transcript correction.")
    parser.add_argument("--no-ollama", action="store_true", help="Skip Ollama and use the rule-based rewriter.")
    parser.add_argument("--rewrite-only", help="Only rewrite this text; do not record or transcribe.")
    parser.add_argument("--audio", help="Use an existing WAV/audio file instead of recording.")
    parser.add_argument("--no-copy-prompt", action="store_true", help="Do not ask whether to copy after generating output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root)
    configure_cache_environment(root)
    ensure_runtime_dirs(root)

    rewriter = build_rewriter(args.ollama_model, use_ollama=not args.no_ollama)
    transcript_corrector = build_corrector(
        args.ollama_model,
        use_ollama=args.use_ollama_corrector and not args.no_ollama,
    )

    if args.rewrite_only:
        corrected_text = transcript_corrector(args.rewrite_only)
        result = VoicePromptResult(
            raw_text=args.rewrite_only,
            corrected_text=corrected_text,
            optimized_prompt=rewriter(corrected_text),
        )
        print(format_result(result))
        if args.no_copy_prompt:
            return 0
        if input("复制优化后的 prompt 到剪贴板？输入 c 复制，其他键跳过：").strip().lower() == "c":
            copy_text(result.optimized_prompt)
            print("已复制。")
        return 0

    if args.audio:
        audio_path = Path(args.audio)
    else:
        input("按 Enter 开始录音。")
        audio_path = record_until_enter(root / "recordings")
        print(f"录音已保存：{audio_path}")

    transcriber = build_transcriber(args, root)
    pipeline = VoicePromptPipeline(
        transcribe=transcriber.transcribe,
        correct_transcript=transcript_corrector,
        rewrite=rewriter,
    )

    print("正在转写、校对和整理，第一次运行可能需要下载模型。")
    try:
        result = pipeline.process_audio(audio_path)
    except Exception as exc:
        print(f"处理失败：{exc}")
        return 1
    print(format_result(result))
    if args.no_copy_prompt:
        return 0

    while True:
        choice = input("输入 c 复制优化 prompt，r 重新录音，q 退出：").strip().lower()
        if choice == "c":
            copy_text(result.optimized_prompt)
            print("已复制。")
        elif choice == "r":
            return main()
        elif choice == "q" or choice == "":
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
