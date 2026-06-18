from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable


class OllamaUnavailable(RuntimeError):
    pass


def _post_json(url: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def _clean_model_response(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    fenced = re.fullmatch(r"```(?:text|markdown|md)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    return cleaned.strip()


class OllamaPromptRewriter:
    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:11434",
        keep_alive: int | str = 0,
        rewrite_style: str = "semantic",
        language: str = "zh",
        post_json: Callable[[str, dict], str] = _post_json,
    ) -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.keep_alive = keep_alive
        self.rewrite_style = rewrite_style
        self.language = language
        self._post_json = post_json

    def rewrite(self, text: str) -> str:
        prompt = self._build_prompt(text)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 20,
                "repeat_penalty": 1.05,
                "num_ctx": 8192,
                "num_predict": 512,
            },
        }

        try:
            raw_response = self._post_json(f"{self.endpoint}/api/generate", payload)
            response = json.loads(raw_response)
        except Exception as exc:
            raise OllamaUnavailable(str(exc)) from exc

        result = _clean_model_response(str(response.get("response", "")))
        if not result:
            raise OllamaUnavailable("Ollama returned an empty response.")
        return result

    def _build_prompt(self, text: str) -> str:
        if self.language == "en":
            return self._build_english_prompt(text)
        return self._build_chinese_prompt(text)

    def _build_chinese_prompt(self, text: str) -> str:
        if self.rewrite_style == "faithful":
            instruction = (
                "把下面口述做忠实整理，尽量保留原意、信息顺序和表达重心。只输出整理后的正文，不要解释。\n"
                "只删除口头禅、停顿、明显重复和识别噪声；不要主动压缩重要细节，不要新增信息。\n"
                "保留全部事实、数字、单位、条件、偏好、否定和不确定表达。"
            )
        elif self.rewrite_style == "semantic":
            instruction = (
                "请像一个表达能力强的中文编辑，先理解说话者真实意图，再把下面口述重新写成逻辑清晰、表达完整、"
                "可直接发送给 AI 或他人的中文正文。只输出整理后的正文，不要解释。\n"
                "不要逐句复述原话；可以重排顺序、合并重复、补足必要连接词和主谓宾关系，"
                "用表达性和逻辑性更强的语言说清楚完整内容。\n"
                "必须保留全部事实、数字、单位、条件、偏好、否定和不确定表达；不要新增信息，不要替说话者做新的决定。"
            )
        else:
            instruction = (
                "把下面口述整理成简洁、准确、通顺的中文正文。只输出整理后的正文，不要解释。\n"
                "保留全部事实、数字、单位、条件、偏好、否定和不确定表达；删除口头禅、停顿和重复；不要新增信息。\n"
                "优先合并成一个自然段，内容较多时最多分成三个自然段。"
            )
        return f"{instruction}\n\n口述：{text}\n\n整理后："

    def _build_english_prompt(self, text: str) -> str:
        if self.rewrite_style == "faithful":
            instruction = (
                "Faithfully clean up the spoken text below. Preserve the original meaning, order, and emphasis. "
                "Only remove filler words, pauses, obvious repetition, and recognition noise. "
                "Do not compress important details or add new information. "
                "Retain all facts, numbers, units, conditions, preferences, negations, and uncertainties. "
                "Output only the cleaned text, no explanations."
            )
        elif self.rewrite_style == "semantic":
            instruction = (
                "You are a skilled English editor. Understand the speaker's true intent and rewrite the spoken text below "
                "into clear, logical, complete written English that can be sent directly to an AI or another person. "
                "Do not paraphrase sentence by sentence; reorder, merge, and complete the structure as needed. "
                "Retain all facts, numbers, units, conditions, preferences, negations, and uncertainties. "
                "Do not add new information or make decisions for the speaker. "
                "Output only the rewritten text, no explanations."
            )
        else:
            instruction = (
                "Clean up the spoken text below into concise, accurate, natural English. "
                "Remove filler words, pauses, and repetition. Retain all facts and key details. "
                "Do not add new information. Prefer one paragraph; use at most three if the content is long. "
                "Output only the cleaned text, no explanations."
            )
        return f"{instruction}\n\nSpoken: {text}\n\nCleaned:"
