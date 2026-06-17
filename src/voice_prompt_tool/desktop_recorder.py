from __future__ import annotations

import datetime as dt
from enum import Enum
from pathlib import Path
from typing import Callable

import numpy as np

from voice_prompt_tool.recorder import write_wav_mono


class RecorderState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


class PauseableAudioRecorder:
    def __init__(
        self,
        output_dir: Path,
        sample_rate: int = 16000,
        stream_factory: Callable[..., object] | None = None,
        timestamp_factory: Callable[[], str] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.sample_rate = sample_rate
        self._stream_factory = stream_factory
        self._timestamp_factory = timestamp_factory or (lambda: dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        self._stream: object | None = None
        self._chunks: list[np.ndarray] = []
        self._output_path: Path | None = None
        self._state = RecorderState.IDLE
        self._activity_level = 0.0

    @property
    def state(self) -> RecorderState:
        return self._state

    @property
    def activity_level(self) -> float:
        return self._activity_level

    def start(self) -> Path:
        if self._state is not RecorderState.IDLE:
            raise RuntimeError("recording is already active")

        if self._stream_factory is None:
            import sounddevice as sd

            self._stream_factory = sd.InputStream

        self._chunks = []
        self._activity_level = 0.0
        self._output_path = self.output_dir / f"recording-{self._timestamp_factory()}.wav"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._stream = self._stream_factory(
            channels=1,
            samplerate=self.sample_rate,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self._state = RecorderState.RECORDING
        return self._output_path

    def pause(self) -> None:
        if self._state is not RecorderState.RECORDING:
            raise RuntimeError("recording is not active")
        self._state = RecorderState.PAUSED

    def resume(self) -> None:
        if self._state is not RecorderState.PAUSED:
            raise RuntimeError("recording is not paused")
        self._state = RecorderState.RECORDING

    def stop(self) -> Path:
        if self._state not in (RecorderState.RECORDING, RecorderState.PAUSED):
            raise RuntimeError("recording is not active")
        if self._stream is None or self._output_path is None:
            raise RuntimeError("recording stream is not initialized")

        self._stream.stop()
        self._stream.close()
        samples = np.concatenate(self._chunks) if self._chunks else np.array([], dtype=np.float32)
        write_wav_mono(self._output_path, samples.tolist(), self.sample_rate)
        output_path = self._output_path
        self._stream = None
        self._output_path = None
        self._state = RecorderState.IDLE
        self._activity_level = 0.0
        return output_path

    def _callback(self, indata, frames, time, status) -> None:  # noqa: ANN001, ARG002
        channel = np.asarray(indata[:, 0], dtype=np.float32)
        self._activity_level = float(np.max(np.abs(channel))) if channel.size else 0.0
        if self._state is RecorderState.RECORDING:
            self._chunks.append(channel.copy())
