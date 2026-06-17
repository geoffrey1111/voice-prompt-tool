from __future__ import annotations

import re

from voice_prompt_tool.transcript_corrector import correct_transcript


FILLERS = (
    "就是",
    "那个",
    "呃",
    "嗯",
    "啊",
    "就",
)

SPOKEN_REPLACEMENTS = (
    (re.compile(r"我们现在来测试一下现在这个(.+?)的一个效果吧"), r"我在测试\1的效果"),
    (re.compile(r"最近我因为在"), "最近我在"),
    (re.compile(r"比较头疼，因为我预算其实是"), "比较头疼，预算是"),
    (re.compile(r"预算其实是"), "预算是"),
    (re.compile(r"本来我是想说"), "本来想"),
    (re.compile(r"几十\s*10\s*块"), "几十块"),
    (re.compile(r"几\s*10\s*块"), "几十块"),
    (re.compile(r"他后面发现现在在买的这个麦克风"), "后来发现现在买的这个麦克风"),
    (re.compile(r"他后面发现现在买的这个麦克风"), "后来发现现在买的这个麦克风"),
    (
        re.compile(r"他除非我离得很近说话，不然他把我的声音都会录的非常的小"),
        "它需要我离得很近说话，否则录到的声音非常小",
    ),
    (re.compile(r"所以我觉得他应该是参数"), "我判断问题在参数上"),
    (re.compile(r"叫什么来看？叫麦克风灵敏度，或者说收音灵敏度太低了"), "问题是麦克风灵敏度，或者说收音灵敏度太低"),
    (re.compile(r"叫什么来着？叫麦克风灵敏度，或者说收音灵敏度太低了"), "问题是麦克风灵敏度，或者说收音灵敏度太低"),
    (re.compile(r"叫什么来看？叫"), "指的是"),
    (re.compile(r"叫什么来着？叫"), "指的是"),
    (re.compile(r"或者说叫"), "或者说"),
    (re.compile(r"收音灵敏度这个参数的话，它是要看参数的话，?"), "收音灵敏度这个参数"),
    (re.compile(r"收音灵敏度这个参数的话，它是要看数字，?"), "收音灵敏度这个参数"),
    (re.compile(r"收音灵敏度这个参数的话，它是要看那个数字，?"), "收音灵敏度这个参数"),
    (re.compile(r"它一般是负数，离零越近的话是灵敏度越好"), "它一般是负数，离 0 越近灵敏度越好"),
    (re.compile(r"现在这款我感觉它灵敏度很差"), "现在这款灵敏度很差"),
    (re.compile(r"而且它也没有在商品页把灵敏度标出来"), "而且商品页没有标出灵敏度"),
    (re.compile(r"所以后面我可能会再重新去挑一款麦克风吧"), "所以后续可能会重新挑一款麦克风"),
    (re.compile(r"因为我在网上有看到说别人说哎"), "虽然网上有人说"),
    (re.compile(r"但实话实说，?"), "但"),
    (re.compile(r"我感觉用起来确实现在这款不是很爽"), "现在这款用起来不太舒服"),
    (re.compile(r"应该要找一个灵敏度更高的一个[。，]?麦克风才行"), "需要找一个灵敏度更高的麦克风"),
    (re.compile(r"应该要找一个灵敏度更高的一个"), "需要找一个灵敏度更高的麦克风"),
    (re.compile(r"麦克风才行"), ""),
    (re.compile(r"但是我也不考虑那种领夹的，那种纽扣那种麦克风"), "但不考虑领夹式、纽扣式麦克风"),
    (re.compile(r"我还是想要这种放在桌面上的"), "还是想要放在桌面上的麦克风"),
)

LINE_BREAK_MARKERS = (
    "最近",
    "本来",
    "后来",
    "我判断",
    "也就是",
    "收音灵敏度这个参数",
    "现在这款",
    "所以后续",
    "虽然",
    "但不考虑",
    "还是想要",
    "首先",
    "后面",
    "正好",
)

ORPHAN_CONNECTORS = {"所以", "然后", "因为", "但是", "但", "而且"}


def _apply_spoken_replacements(text: str) -> str:
    cleaned = text
    for pattern, replacement in SPOKEN_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned

def _strip_fillers(text: str) -> str:
    cleaned = text
    for filler in FILLERS:
        cleaned = cleaned.replace(filler, "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ，,。")


def _add_semantic_line_breaks(text: str) -> str:
    cleaned = text
    for marker in LINE_BREAK_MARKERS:
        cleaned = cleaned.replace(marker, f"\n{marker}")
    cleaned = re.sub(r"([。！？?])", r"\1\n", cleaned)
    cleaned = re.sub(r"\n+", "\n", cleaned)
    return cleaned.strip()


def _normalize_punctuation(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip(" ，,。")
        if not stripped:
            continue
        if stripped in ORPHAN_CONNECTORS:
            continue
        if stripped.endswith(("。", "？", "！")):
            lines.append(stripped)
        else:
            lines.append(f"{stripped}。")
    return "\n".join(lines)


def polish_spoken_text(text: str) -> str:
    corrected = correct_transcript(text)
    cleaned = _apply_spoken_replacements(corrected)
    cleaned = _strip_fillers(cleaned)
    cleaned = _add_semantic_line_breaks(cleaned)
    cleaned = _normalize_punctuation(cleaned)
    return cleaned
