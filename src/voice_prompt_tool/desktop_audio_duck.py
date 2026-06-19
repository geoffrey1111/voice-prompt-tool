from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Process names (lowercase) whose audio will be ducked during recording.
_MUSIC_PROCS: frozenset[str] = frozenset({
    "spotify.exe",
    "cloudmusic.exe",    # 网易云音乐
    "qqmusic.exe",       # QQ音乐
    "kgmusic.exe",       # 酷狗音乐
    "kwmusic.exe",       # 酷我音乐
    "music.exe",         # Apple Music (Windows)
    "vlc.exe",
    "wmplayer.exe",
    "foobar2000.exe",
    "aimp.exe",
    "musicbee.exe",
    "itunes.exe",
    "ximalaya.exe",      # 喜马拉雅
    "lizhi.exe",         # 荔枝FM
    "ncm.exe",           # 网易云音乐旧版
})

# Reduce each app's volume to this fraction of its current level during recording.
# 0.15 = 15% of original (e.g. 80% → 12%).  Change to taste.
DUCK_RATIO = 0.15


class AudioDucker:
    """Lowers music-application volume while recording, restores it on stop.

    Depends on ``pycaw``; silently no-ops if it is not installed.
    """

    def __init__(self) -> None:
        self._saved: dict[int, float] = {}  # pid → original volume scalar

    def duck(self) -> None:
        """Lower audio of any running music apps."""
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore[import]
        except ImportError:
            _log.debug("pycaw not installed; audio ducking skipped")
            return

        self._saved.clear()
        try:
            for session in AudioUtilities.GetAllSessions():
                proc = session.Process
                if proc is None:
                    continue
                if proc.name().lower() not in _MUSIC_PROCS:
                    continue
                vol = session.SimpleAudioVolume
                if vol is None:
                    continue
                current = vol.GetMasterVolume()
                if current < 0.01:
                    continue  # already silent — nothing to duck
                self._saved[proc.pid] = current
                vol.SetMasterVolume(current * DUCK_RATIO, None)
                _log.debug("ducked %s (pid=%d): %.2f → %.2f",
                           proc.name(), proc.pid, current, current * DUCK_RATIO)
        except Exception:
            _log.exception("audio duck failed")

    def restore(self) -> None:
        """Restore previously ducked application volumes."""
        if not self._saved:
            return
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore[import]
        except ImportError:
            self._saved.clear()
            return

        try:
            for session in AudioUtilities.GetAllSessions():
                proc = session.Process
                if proc is None:
                    continue
                original = self._saved.get(proc.pid)
                if original is None:
                    continue
                vol = session.SimpleAudioVolume
                if vol is not None:
                    vol.SetMasterVolume(original, None)
                    _log.debug("restored %s (pid=%d) → %.2f", proc.name(), proc.pid, original)
        except Exception:
            _log.exception("audio restore failed")
        finally:
            self._saved.clear()
