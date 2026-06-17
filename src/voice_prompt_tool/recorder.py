from __future__ import annotations

import datetime as dt
import wave
from pathlib import Path
from typing import Iterable


def write_wav_mono(path: Path, samples: Iterable[float], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    for sample in samples:
        clipped = max(-1.0, min(1.0, float(sample)))
        value = int(clipped * 32767)
        pcm.extend(value.to_bytes(2, byteorder="little", signed=True))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(pcm))


def record_until_enter(output_dir: Path, sample_rate: int = 16000) -> Path:
    import numpy as np
    import sounddevice as sd

    chunks = []

    def callback(indata, frames, time, status) -> None:  # noqa: ANN001
        if status:
            print(f"录音状态提示：{status}")
        chunks.append(indata[:, 0].copy())

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(output_dir) / f"recording-{timestamp}.wav"

    print("正在录音。说完后按 Enter 停止。")
    with sd.InputStream(channels=1, samplerate=sample_rate, dtype="float32", callback=callback):
        input()

    if chunks:
        samples = np.concatenate(chunks)
    else:
        samples = np.array([], dtype=np.float32)

    write_wav_mono(output_path, samples.tolist(), sample_rate)
    return output_path
