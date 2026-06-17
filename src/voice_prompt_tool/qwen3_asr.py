from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


ModelLoader = Callable[..., object]


class Qwen3ASRTranscriber:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-ASR-0.6B",
        device: str = "cpu",
        language: str | None = "Chinese",
        max_new_tokens: int = 512,
        max_inference_batch_size: int = 1,
        model_loader: ModelLoader | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.language = language
        self.max_new_tokens = max_new_tokens
        self.max_inference_batch_size = max_inference_batch_size
        self._model_loader = model_loader
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model

        dtype_name = "bfloat16" if self.device.startswith("cuda") else "float32"
        device_map = self.device if self.device.startswith("cuda") else "cpu"
        kwargs = {
            "model_name": self.model_name,
            "dtype_name": dtype_name,
            "device_map": device_map,
            "max_inference_batch_size": self.max_inference_batch_size,
            "max_new_tokens": self.max_new_tokens,
        }
        if self._model_loader is not None:
            self._model = self._model_loader(**kwargs)
            return self._model

        import torch
        from qwen_asr import Qwen3ASRModel

        dtype = torch.bfloat16 if dtype_name == "bfloat16" else torch.float32
        self._model = Qwen3ASRModel.from_pretrained(
            self.model_name,
            dtype=dtype,
            device_map=device_map,
            max_inference_batch_size=self.max_inference_batch_size,
            max_new_tokens=self.max_new_tokens,
        )
        return self._model

    def warm_up(self) -> None:
        self._load_model()

    def transcribe(self, audio_path: Path) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(path)

        model = self._load_model()
        results = model.transcribe(audio=str(path), language=self.language)
        if not results:
            return ""
        return _result_text(results[0]).strip()


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("text", ""))
    return str(getattr(result, "text", ""))
