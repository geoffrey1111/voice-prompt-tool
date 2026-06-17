from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Callable


class SenseVoiceTranscriber:
    def __init__(
        self,
        model_dir: Path,
        device: str = "cpu",
        language: str = "zh",
        recordings_dir: Path | None = None,
        recordings_ascii_dir: Path | None = None,
        model_factory: Callable[[], object] | None = None,
        postprocess: Callable[[str], str] | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.device = device
        self.language = language
        self.recordings_dir = Path(recordings_dir) if recordings_dir else None
        self.recordings_ascii_dir = Path(recordings_ascii_dir) if recordings_ascii_dir else None
        self._model_factory = model_factory
        self._postprocess = postprocess
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model

        if self._model_factory is not None:
            self._model = self._model_factory()
            return self._model

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from funasr import AutoModel

            self._model = AutoModel(
                model=str(self.model_dir),
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device=self.device,
                disable_update=True,
                disable_pbar=True,
                log_level="ERROR",
            )
        return self._model

    def warm_up(self) -> None:
        self._load_model()

    def _audio_path_for_backend(self, audio_path: Path) -> Path:
        path = Path(audio_path)
        if not self.recordings_dir or not self.recordings_ascii_dir:
            return path

        try:
            relative_path = path.resolve().relative_to(self.recordings_dir.resolve())
        except ValueError:
            return path

        return self.recordings_ascii_dir / relative_path

    def _clean_text(self, text: str) -> str:
        if self._postprocess is not None:
            text = self._postprocess(text)
        else:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            text = rich_transcription_postprocess(text)
        return text.lstrip("。,.，、 ").strip()

    def transcribe(self, audio_path: Path) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(path)

        backend_path = self._audio_path_for_backend(path)
        model = self._load_model()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            results = model.generate(
                input=str(backend_path),
                cache={},
                language=self.language,
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
                disable_pbar=True,
            )
        return "".join(self._clean_text(item.get("text", "")) for item in results).strip()
