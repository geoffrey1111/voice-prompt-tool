from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from voice_prompt_tool.cli import build_corrector, build_rewriter, build_transcriber
from voice_prompt_tool.desktop_ollama import OllamaServiceManager
from voice_prompt_tool.desktop_processing import process_recording_in_stages
from voice_prompt_tool.desktop_settings import DesktopSettings
from voice_prompt_tool.desktop_vocab import VocabularyManager
from voice_prompt_tool.paths import configure_cache_environment, ensure_runtime_dirs
from voice_prompt_tool.pipeline import VoicePromptResult


@dataclass
class WarmupBundle:
    transcriber: object
    transcribe: Callable[[Path], str]
    correct_transcript: Callable[[str], str]
    rewrite: Callable[[str], str]
    ollama_manager: OllamaServiceManager


def ollama_keep_alive_for_settings(settings: DesktopSettings) -> str:
    if settings.idle_release_minutes <= 0:
        return "24h"
    return f"{settings.idle_release_minutes}m"


def build_warmup_bundle(root: Path, settings: DesktopSettings | None = None) -> WarmupBundle:
    root = Path(root)
    settings = settings or DesktopSettings()
    language = settings.asr_language
    if language == "en":
        args = argparse.Namespace(
            asr_backend="whisper",
            asr_device="cpu",
            asr_compute_type="int8",
            whisper_model="medium",
            asr_language="en",
        )
    else:
        args = argparse.Namespace(
            asr_backend="sensevoice",
            asr_device="cpu",
            asr_compute_type="int8",
            whisper_model="large-v3",
            asr_language="zh",
        )
    transcriber = build_transcriber(args, root)
    base_corrector = build_corrector("qwen3:4b-instruct", use_ollama=False)

    def correct_with_vocab(text: str) -> str:
        # Reload from disk on every call (cheap — small JSON file) so vocab edits made in
        # Settings take effect immediately without requiring a full model re-warmup.
        vocab = VocabularyManager(root)
        vocab.load()
        return base_corrector(vocab.apply(text))

    return WarmupBundle(
        transcriber=transcriber,
        transcribe=transcriber.transcribe,
        correct_transcript=correct_with_vocab,
        rewrite=build_rewriter(
            "qwen3:4b-instruct",
            use_ollama=True,
            keep_alive=ollama_keep_alive_for_settings(settings),
            rewrite_style=settings.rewrite_style,
            language=language,
        ),
        ollama_manager=OllamaServiceManager(root),
    )


class DesktopModelWarmup:
    def __init__(
        self,
        root: Path,
        bundle_factory: Callable[[Path], WarmupBundle] | None = None,
        settings_provider: Callable[[], DesktopSettings] | None = None,
    ) -> None:
        self.root = Path(root)
        self._bundle_factory = bundle_factory
        self._settings_provider = settings_provider or DesktopSettings
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._refresh_thread: threading.Thread | None = None
        self._bundle: WarmupBundle | None = None
        self._error: BaseException | None = None
        self._stage = "模型未加载"
        self._progress_percent = 0

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._bundle is not None and self._error is None

    @property
    def is_warming(self) -> bool:
        return self._thread is not None and not self._ready.is_set()

    @property
    def status_text(self) -> str:
        if self._error is not None:
            return f"预热失败：{self._error}"
        if self.is_ready:
            return "模型已就绪"
        if self.is_warming:
            return self._stage or "模型预热中"
        return self._stage or "模型未加载"

    @property
    def progress_percent(self) -> int:
        return self._progress_percent

    def start(self) -> None:
        with self._lock:
            should_start_thread = self._thread is None or (
                self._ready.is_set() and (self._bundle is None or self._error is not None)
            )
            if should_start_thread:
                self._ready.clear()
                self._error = None
                self._bundle = None
                self._stage = "准备加载本地模型"
                self._progress_percent = 5
                self._thread = threading.Thread(target=self._run, name="voice-prompt-warmup", daemon=True)
                self._thread.start()
                return
            if not self._ready.is_set() or self._bundle is None:
                return
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return
            self._refresh_thread = threading.Thread(
                target=self._refresh_ollama,
                name="voice-prompt-ollama-refresh",
                daemon=True,
            )
            self._refresh_thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        with self._lock:
            should_start = self._thread is None
        if should_start:
            self.start()
        ready = self._ready.wait(timeout)
        if ready:
            self._raise_if_failed()
        return ready

    def process(
        self,
        audio_path: Path,
        on_transcript: Callable[[VoicePromptResult], None] | None = None,
    ) -> VoicePromptResult:
        self.wait()
        bundle = self._require_bundle()
        return process_recording_in_stages(
            audio_path=audio_path,
            root=self.root,
            transcribe=bundle.transcribe,
            correct_transcript=bundle.correct_transcript,
            rewrite=bundle.rewrite,
            ollama_manager=bundle.ollama_manager,
            on_transcript=on_transcript,
            stop_ollama_after=False,
        )

    def rewrite_text(self, text: str) -> str:
        bundle = self._require_bundle()
        return bundle.rewrite(text)

    def update_keep_alive(self, settings: DesktopSettings) -> None:
        """Push a changed idle-release setting into the already-warmed rewriter/corrector
        without requiring a full re-warmup. Without this, a live Ollama rewriter keeps using
        whatever keep_alive value was baked in at warmup time, so changing the setting in the
        UI silently has no effect until the app restarts."""
        bundle = self._bundle
        if bundle is None:
            return
        keep_alive = ollama_keep_alive_for_settings(settings)
        for fn in (bundle.rewrite, bundle.correct_transcript):
            target = getattr(fn, "ollama_rewriter", None) or getattr(fn, "ollama_corrector", None)
            if target is not None:
                target.set_keep_alive(keep_alive)

    def transcribe_only(self, audio_path: Path) -> VoicePromptResult:
        bundle = self._require_bundle()
        raw_text = bundle.transcribe(Path(audio_path)).strip()
        if not raw_text:
            raise ValueError("没有识别到有效语音内容，请靠近麦克风重新录制。")
        corrected_text = bundle.correct_transcript(raw_text).strip()
        if not corrected_text:
            raise ValueError("转写校对后为空，请重新录制。")
        return VoicePromptResult(raw_text=raw_text, corrected_text=corrected_text, optimized_prompt=corrected_text)

    def shutdown(self) -> None:
        self.release()

    def release(self) -> None:
        if self._thread is not None:
            try:
                self.wait(timeout=0.2)
            except RuntimeError:
                pass
        refresh_thread = self._refresh_thread
        if refresh_thread is not None and refresh_thread.is_alive():
            refresh_thread.join(timeout=0.2)
        bundle = self._bundle
        if bundle is not None:
            stop_local_processes = getattr(bundle.ollama_manager, "stop_local_processes", None)
            if callable(stop_local_processes):
                stop_local_processes()
            else:
                bundle.ollama_manager.stop_if_started()
        with self._lock:
            self._bundle = None
            self._thread = None
            self._refresh_thread = None
            self._error = None
            self._ready.clear()
            self._stage = "模型已释放"
            self._progress_percent = 0

    def _run(self) -> None:
        try:
            self._set_stage("准备运行环境", 10)
            configure_cache_environment(self.root)
            ensure_runtime_dirs(self.root)
            self._set_stage("加载语音识别模型", 25)
            if self._bundle_factory is not None:
                bundle = self._bundle_factory(self.root)
            else:
                bundle = build_warmup_bundle(self.root, self._settings_provider())
            self._warm_transcriber(bundle)
            self._set_stage("启动本地 Qwen 模型", 65)
            self._warm_ollama(bundle)
            with self._lock:
                self._bundle = bundle
                self._stage = "模型已就绪"
                self._progress_percent = 100
        except BaseException as exc:
            with self._lock:
                self._error = exc
                self._stage = f"模型加载失败：{exc}"
        finally:
            self._ready.set()

    @staticmethod
    def _warm_transcriber(bundle: WarmupBundle) -> None:
        warm_up = getattr(bundle.transcriber, "warm_up", None)
        if callable(warm_up):
            warm_up()

    @staticmethod
    def _warm_ollama(bundle: WarmupBundle) -> None:
        try:
            bundle.ollama_manager.start_if_needed()
            bundle.rewrite("预热本地模型。")
        except Exception:
            pass

    def _refresh_ollama(self) -> None:
        bundle = self._bundle
        if bundle is not None:
            self._warm_ollama(bundle)

    def _set_stage(self, stage: str, progress_percent: int) -> None:
        with self._lock:
            self._stage = stage
            self._progress_percent = max(0, min(100, int(progress_percent)))

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"本地模型预热失败：{self._error}") from self._error

    def _require_bundle(self) -> WarmupBundle:
        self._raise_if_failed()
        if self._bundle is None:
            raise RuntimeError("本地模型尚未完成预热。")
        return self._bundle
