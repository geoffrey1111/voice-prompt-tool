from __future__ import annotations

import json
from typing import Callable

from voice_prompt_tool.ollama_rewriter import OllamaUnavailable, _post_json
from voice_prompt_tool.transcript_corrector import guard_corrected_transcript


class OllamaTranscriptCorrector:
    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:11434",
        post_json: Callable[[str, dict], str] = _post_json,
    ) -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self._post_json = post_json

    def correct(self, text: str) -> str:
        prompt = (
            "你是一个校对语音转写文本的助手。请只做转写校对，不要总结、不要改写成任务、不要新增原文没有的信息。\n\n"
            "校对规则：\n"
            "1. 修正明显的错别字、同音误识别、英文产品名和专业术语，例如 Codex、AI、3D、JSON。\n"
            "2. 保留所有数字、单位、选项和不确定表达，例如 5000、3500、4000、3000、可能、应该、估计、还是。\n"
            "3. 可以添加标点和轻微断句，让文本更容易阅读。\n"
            "4. 不要删除用户重复提到但可能有用的信息，不要把多个备选项合并成单一结论。\n"
            "5. 只输出校对后的文本。\n\n"
            f"原始转写：{text}"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": 0,
        }

        try:
            raw_response = self._post_json(f"{self.endpoint}/api/generate", payload)
            response = json.loads(raw_response)
        except Exception as exc:
            raise OllamaUnavailable(str(exc)) from exc

        corrected = str(response.get("response", "")).strip()
        if not corrected:
            raise OllamaUnavailable("Ollama returned an empty transcript correction.")
        return guard_corrected_transcript(text, corrected)
