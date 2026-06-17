from __future__ import annotations

import re


FILLER_PATTERNS = (
    "就是",
    "那个",
    "然后",
    "呃",
    "嗯",
    "嘛",
)


DOMAIN_REPLACEMENTS = (
    (re.compile("colex", re.IGNORECASE), "Codex"),
    (re.compile("codex", re.IGNORECASE), "Codex"),
    (re.compile(r"\bai\b", re.IGNORECASE), "AI"),
    (re.compile("你和程度"), "拟合程度"),
    (re.compile("契合程度"), "拟合程度"),
)


def _clean_spoken_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    for filler in FILLER_PATTERNS:
        cleaned = cleaned.replace(filler, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
    return cleaned


def normalize_transcript(text: str) -> str:
    cleaned = _clean_spoken_text(text)
    for pattern, replacement in DOMAIN_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = cleaned.replace("给AI", "给 AI")
    return cleaned


def _is_quality_evaluation_request(text: str) -> bool:
    signals = ("质量", "效率", "第一次测试", "测试", "评估", "相似度", "拟合程度", "完整保留", "保留")
    return sum(1 for signal in signals if signal in text) >= 3


def _rewrite_quality_evaluation_request(cleaned: str) -> str:
    target = "Codex" if "codex" in cleaned.casefold() else "AI"
    return (
        f"请让 {target} 处理下面这段语音输入测试文本，目标是评估“语音识别 + AI prompt 优化”的质量、效率和语义保真度。\n\n"
        f"原始识别文本：\n{cleaned}\n\n"
        "任务：\n"
        "1. 完整保留原始识别文本，不要把它压缩成另一个任务。\n"
        "2. 基于原始识别文本，整理出一个更清晰、更适合 AI 执行的 prompt。\n"
        "3. 对比原始口述意图和优化后的 prompt，指出有没有遗漏、误解或过度改写。\n"
        "4. 评估优化后的 prompt 与原始口述意图的拟合程度，并说明判断依据。\n\n"
        "输出要求：\n"
        "- 原始识别文本\n"
        "- 优化后的 AI prompt\n"
        "- 质量、效率和语义保真度评价\n"
        "- 拟合程度评分或简短结论\n"
        "- 主要丢失或需要人工确认的点"
    )


def rewrite_prompt(text: str) -> str:
    """Turn casual dictated text into a concise AI-ready prompt."""
    cleaned = normalize_transcript(text)
    if not cleaned:
        raise ValueError("口述内容为空，无法改写。")

    if _is_quality_evaluation_request(cleaned):
        return _rewrite_quality_evaluation_request(cleaned)

    lowered = cleaned.casefold()
    wants_bug_review = any(term in lowered for term in ("bug", "问题", "哪里有问题"))
    wants_small_change = any(term in cleaned for term in ("不要改太多", "别改太多", "最小"))
    target = "Codex" if "codex" in lowered else "AI"

    focus = "潜在 bug、边界条件、错误处理和缺失测试" if wants_bug_review else "目标、约束、输出格式和下一步行动"
    change_rule = "如需修改代码，请优先采用最小修改，避免不必要的重构。" if wants_small_change else "请先说明判断依据，再给出建议。"

    return (
        f"请让 {target} 根据下面的口述需求执行任务：\n"
        f"{cleaned}\n\n"
        f"要求：\n"
        f"1. 先整理任务目标和关键约束。\n"
        f"2. 重点关注{focus}。\n"
        f"3. {change_rule}\n"
        f"4. 输出要清晰、可执行，避免扩写无关内容。"
    )
