from __future__ import annotations

import json
from pathlib import Path

# Average seconds a person spends typing one Chinese/English character by hand.
# Used only to produce a rough "time saved" estimate for the usage dashboard.
DEFAULT_SECONDS_PER_TYPED_CHAR = 0.6


def usage_log_path(root: Path) -> Path:
    return Path(root) / "usage_log.jsonl"


def log_usage(
    root: Path,
    mode: str,
    audio_seconds: float,
    raw_chars: int,
    final_chars: int,
    success: bool,
    timestamp: float,
    seconds_per_typed_char: float = DEFAULT_SECONDS_PER_TYPED_CHAR,
) -> None:
    """Append one JSON-Lines record for a completed AI-mode or dictation interaction.

    Local-only, never uploaded. Feeds the (separately built) usage dashboard: counts by
    day/week/month, estimated time saved, keyword/time-of-day distribution.
    """
    estimated_typing_seconds = final_chars * seconds_per_typed_char
    seconds_saved = max(0.0, estimated_typing_seconds - audio_seconds)
    record = {
        "timestamp": timestamp,
        "mode": mode,
        "audio_seconds": round(audio_seconds, 2),
        "raw_chars": raw_chars,
        "final_chars": final_chars,
        "success": success,
        "seconds_saved": round(seconds_saved, 2),
    }
    path = usage_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_usage_log(root: Path) -> list[dict]:
    path = usage_log_path(root)
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records
