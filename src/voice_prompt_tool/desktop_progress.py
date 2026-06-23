from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_ESTIMATES_SECONDS = {
    "asr": 4.0,
    "rewrite": 6.0,
}
_MAX_SAMPLES = 8


def _stats_path(root: Path) -> Path:
    return Path(root) / "stage_durations.json"


class StageTimeEstimator:
    """Tracks a rolling window of recent stage durations to drive a pseudo-progress bar.

    There's no real completion percentage available from ASR or the Ollama /api/generate
    call without streaming token-by-token, so this estimates "percent done" as
    elapsed-time / typical-past-duration, capped below 100% until the stage actually
    finishes. Purely cosmetic — it has zero bearing on correctness, only on perceived
    responsiveness while the user waits.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._samples: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        path = _stats_path(self.root)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._samples = {k: [float(v) for v in vs][-_MAX_SAMPLES:] for k, vs in data.items()}
        except Exception:
            self._samples = {}

    def _save(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            _stats_path(self.root).write_text(json.dumps(self._samples), encoding="utf-8")
        except Exception:
            pass

    def estimate(self, stage: str) -> float:
        samples = self._samples.get(stage)
        if not samples:
            return _DEFAULT_ESTIMATES_SECONDS.get(stage, 5.0)
        return sum(samples) / len(samples)

    def record(self, stage: str, duration_seconds: float) -> None:
        if duration_seconds <= 0:
            return
        samples = self._samples.setdefault(stage, [])
        samples.append(duration_seconds)
        del samples[:-_MAX_SAMPLES]
        self._save()

    def progress_fraction(self, stage: str, elapsed_seconds: float, cap: float = 0.92) -> float:
        """Fraction of estimated duration elapsed, capped so it never visually hits 100%
        before the stage actually completes (completion itself snaps the UI to 100%)."""
        estimate = self.estimate(stage)
        if estimate <= 0:
            return 0.0
        return max(0.0, min(cap, elapsed_seconds / estimate))
