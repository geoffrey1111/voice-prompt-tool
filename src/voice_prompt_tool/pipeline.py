from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class VoicePromptResult:
    raw_text: str
    optimized_prompt: str
    corrected_text: str = ""


class VoicePromptPipeline:
    def __init__(
        self,
        transcribe: Callable[[Path], str],
        rewrite: Callable[[str], str],
        correct_transcript: Callable[[str], str] | None = None,
    ) -> None:
        self._transcribe = transcribe
        self._rewrite = rewrite
        self._correct_transcript = correct_transcript or (lambda text: text)

    def process_audio(self, audio_path: Path) -> VoicePromptResult:
        resolved_path = Path(audio_path)
        if not resolved_path.exists():
            raise FileNotFoundError(resolved_path)

        raw_text = self._transcribe(resolved_path).strip()
        if not raw_text:
            raise ValueError("没有识别到有效语音内容，请靠近麦克风重新录制。")
        corrected_text = self._correct_transcript(raw_text).strip()
        if not corrected_text:
            raise ValueError("转写校对后为空，请重新录制。")
        optimized_prompt = self._rewrite(corrected_text).strip()
        return VoicePromptResult(
            raw_text=raw_text,
            corrected_text=corrected_text,
            optimized_prompt=optimized_prompt,
        )
