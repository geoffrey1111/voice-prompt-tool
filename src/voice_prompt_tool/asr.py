from __future__ import annotations

from pathlib import Path
from typing import Callable


DEFAULT_INITIAL_PROMPT = (
    "以下是普通话口述，可能包含 Codex、Claude Code、Cloud Code、ChatGPT、GPT、Blender、3D、JSON、"
    "面数、头部、身体、下身、流程图、账号、麦克风、灵敏度。请准确转写数字和英文术语。"
)

DEFAULT_HOTWORDS = "Codex Claude Code Cloud Code ChatGPT GPT Blender 3D JSON 面数 头部 身体 下身 流程图 账号 麦克风 灵敏度"


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_size: str,
        cache_dir: Path,
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
        initial_prompt: str = DEFAULT_INITIAL_PROMPT,
        hotwords: str = DEFAULT_HOTWORDS,
        model_factory: Callable[[], object] | None = None,
    ) -> None:
        self.model_size = model_size
        self.cache_dir = Path(cache_dir)
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt
        self.hotwords = hotwords
        self._model_factory = model_factory
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self._model_factory is not None:
            self._model = self._model_factory()
            return self._model

        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=str(self.cache_dir),
        )
        return self._model

    def transcribe(self, audio_path: Path) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(path)

        model = self._load_model()
        segments, _info = model.transcribe(
            str(path),
            language=self.language,
            vad_filter=True,
            beam_size=5,
            initial_prompt=self.initial_prompt,
            hotwords=self.hotwords,
        )
        return "".join(segment.text.strip() for segment in segments).strip()
