from __future__ import annotations

import re

from voice_prompt_tool.prompt_rewriter import normalize_transcript


DOMAIN_FIXES = (
    (re.compile("3d", re.IGNORECASE), "3D"),
    (re.compile("ai", re.IGNORECASE), "AI"),
    (re.compile("json", re.IGNORECASE), "JSON"),
    (re.compile(r"几\s*10\s*块"), "几十块"),
    (re.compile(r"几十\s*10\s*块"), "几十块"),
    (re.compile("gpt", re.IGNORECASE), "GPT"),
    (re.compile("colex", re.IGNORECASE), "Codex"),
    (re.compile("codeex", re.IGNORECASE), "Codex"),
    (re.compile("codex", re.IGNORECASE), "Codex"),
    (re.compile("cloud code", re.IGNORECASE), "Cloud Code"),
    (re.compile("积于"), "基于"),
    (re.compile("转移工具"), "转译工具"),
    (re.compile("你和程度"), "拟合程度"),
    (re.compile("机型"), "畸形"),
    (re.compile("角色的例会"), "角色的立绘"),
    (re.compile("模型重新稍升好了"), "模型重新上传好了"),
    (re.compile("溜出来"), "溢出来"),
    (re.compile("指甲指甲"), "指甲"),
    (re.compile("溢出来的那种模型"), "溢出来的那种畸形"),
    (re.compile(r"要割(\d+)面"), r"要到\1面"),
    (re.compile(r"要加(\d+)面"), r"要到\1面"),
    (re.compile(r"要改(\d+)面"), r"要到\1面"),
    (re.compile(r"需要增加(\d+)面"), r"要到\1面"),
    (re.compile(r"可能增加(\d+)面"), r"可能要到\1面"),
)


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def correct_transcript(text: str) -> str:
    corrected = normalize_transcript(text).lstrip("。,.，、 ")
    for pattern, replacement in DOMAIN_FIXES:
        corrected = pattern.sub(replacement, corrected)
    corrected = re.sub(r"\s+", " ", corrected).strip()
    corrected = corrected.replace("3D生成", "3D 生成")
    corrected = corrected.replace("AI看的", "AI 看的")
    return corrected


def guard_corrected_transcript(raw_text: str, candidate: str) -> str:
    raw_numbers = _numbers(raw_text)
    candidate_numbers = _numbers(candidate)
    if any(number not in candidate_numbers for number in raw_numbers):
        return correct_transcript(raw_text)

    if len(candidate.strip()) < max(20, int(len(raw_text.strip()) * 0.55)):
        return correct_transcript(raw_text)

    return correct_transcript(candidate)
