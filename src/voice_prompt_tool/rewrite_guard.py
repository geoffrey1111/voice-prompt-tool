from __future__ import annotations

import re

from voice_prompt_tool.text_polisher import polish_spoken_text
from voice_prompt_tool.transcript_corrector import correct_transcript


INVENTED_FORMAT_TERMS = (
    "JSON",
    "输出要求",
    "约束：",
    "重点关注：",
    "请让 AI",
    "请让 Codex",
    "返回调整后的",
)

PROTECTED_EXACT_TERMS = (
    "桌面",
    "麦克风",
    "灵敏度",
    "商品页",
    "领夹",
    "纽扣",
    "Codex",
    "Cloud Code",
    "GPT",
    "3D",
    "JSON",
)

NEGATION_SIGNALS = ("不考虑", "不要", "不能", "不需要", "不想", "没有")
NEGATION_PRESERVERS = ("不", "没", "无", "非", "排除", "避免")
UNCERTAINTY_SIGNALS = ("可能", "估计", "应该", "大概", "也许")
UNCERTAINTY_PRESERVERS = ("可能", "估计", "应该", "大概", "也许", "倾向", "暂定")


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def _candidate_drops_protected_meaning(normalized: str, candidate: str) -> bool:
    for term in PROTECTED_EXACT_TERMS:
        if term in normalized and term not in candidate:
            return True

    if any(signal in normalized for signal in NEGATION_SIGNALS):
        if not any(preserver in candidate for preserver in NEGATION_PRESERVERS):
            return True

    if any(signal in normalized for signal in UNCERTAINTY_SIGNALS):
        if not any(preserver in candidate for preserver in UNCERTAINTY_PRESERVERS):
            return True

    return False


def _candidate_loses_fidelity(raw_text: str, candidate: str) -> bool:
    normalized = correct_transcript(raw_text)
    normalized_numbers = _numbers(normalized)
    candidate_numbers = _numbers(candidate)
    if any(number not in candidate_numbers for number in normalized_numbers):
        return True

    if _candidate_drops_protected_meaning(normalized, candidate):
        return True

    if len(candidate.strip()) < max(30, int(len(normalized) * 0.45)):
        return True

    for term in INVENTED_FORMAT_TERMS:
        if term in candidate and term not in normalized:
            return True

    return False


def guard_rewrite_result(raw_text: str, candidate: str) -> str:
    stripped_candidate = candidate.strip()
    if not stripped_candidate:
        return polish_spoken_text(raw_text)

    if _candidate_loses_fidelity(raw_text, stripped_candidate):
        return polish_spoken_text(raw_text)

    return stripped_candidate
