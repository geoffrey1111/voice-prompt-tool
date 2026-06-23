from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class VocabEntry:
    term: str                  # correct canonical spelling, e.g. "拟合度"
    aliases: list[str]         # known wrong ASR outputs for this term, e.g. ["你和度", "意合度"]


# Built-in industry presets. Each is a list of (term, [aliases]) pairs covering common
# domain terms that generic ASR/correction tends to mis-recognize. Not exhaustive — meant
# as a useful starting point that users extend with their own custom entries.
PRESET_VOCAB: dict[str, list[tuple[str, list[str]]]] = {
    "game_dev": [
        ("拟合度", ["你和度", "意合度", "契合程度"]),
        ("立绘", ["例会", "立会"]),
        ("畸形", ["机型"]),
        ("贴图", ["贴途"]),
        ("骨骼绑定", ["骨格绑定"]),
        ("法线贴图", ["法向贴图"]),
        ("受击动画", ["受机动画"]),
        ("掉帧", ["掉真"]),
    ],
    "medical": [
        ("血压", ["雪压"]),
        ("处方", ["出方"]),
        ("复诊", ["副诊"]),
        ("造影剂", ["遭影剂"]),
        ("肌酐", ["鸡丁"]),
    ],
    "legal": [
        ("管辖权", ["管辛权"]),
        ("仲裁", ["种裁"]),
        ("举证责任", ["举正责任"]),
        ("诉讼时效", ["诉讼时校"]),
    ],
    "ecommerce": [
        ("客单价", ["客单家"]),
        ("退换货", ["退环货"]),
        ("发货时效", ["发货时校"]),
        ("售后", ["售后"]),
        ("复购率", ["复构率"]),
    ],
    "media": [
        ("流量", ["留量"]),
        ("涨粉", ["长粉"]),
        ("完播率", ["完播律"]),
        ("文案", ["文按"]),
    ],
}

PRESET_LABELS: dict[str, str] = {
    "general": "通用（不叠加预设）",
    "game_dev": "游戏开发",
    "medical": "医疗",
    "legal": "法律",
    "ecommerce": "电商",
    "media": "自媒体",
}


def vocab_path(root: Path) -> Path:
    return Path(root) / "vocab.json"


class VocabularyManager:
    """Biases ASR output towards user/industry-specific terms.

    Applied right after raw ASR transcription, before the generic rule-based corrector.
    Two passes: exact alias replacement, then a fuzzy pinyin pass that catches
    near-homophone mis-recognitions the user never explicitly listed.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.industry = "general"
        self.entries: list[VocabEntry] = []

    def load(self) -> None:
        path = vocab_path(self.root)
        if not path.exists():
            self.industry = "general"
            self.entries = []
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.industry = "general"
            self.entries = []
            return
        self.industry = str(data.get("industry", "general"))
        self.entries = [
            VocabEntry(term=str(e.get("term", "")), aliases=[str(a) for a in e.get("aliases", [])])
            for e in data.get("entries", [])
            if e.get("term")
        ]

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        vocab_path(self.root).write_text(
            json.dumps(
                {"industry": self.industry, "entries": [asdict(e) for e in self.entries]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def set_custom_entries_from_lines(self, lines: list[str]) -> None:
        """Parse "错误词=正确词" lines (one per line) into custom entries, replacing existing ones."""
        entries: dict[str, VocabEntry] = {}
        for line in lines:
            line = line.strip()
            if not line or "=" not in line:
                continue
            alias, term = line.split("=", 1)
            alias, term = alias.strip(), term.strip()
            if not alias or not term:
                continue
            if term not in entries:
                entries[term] = VocabEntry(term=term, aliases=[])
            if alias not in entries[term].aliases:
                entries[term].aliases.append(alias)
        self.entries = list(entries.values())

    def custom_entries_as_lines(self) -> list[str]:
        lines: list[str] = []
        for entry in self.entries:
            for alias in entry.aliases:
                lines.append(f"{alias}={entry.term}")
        return lines

    def _active_entries(self) -> list[VocabEntry]:
        preset = PRESET_VOCAB.get(self.industry, [])
        merged: dict[str, VocabEntry] = {term: VocabEntry(term=term, aliases=list(aliases)) for term, aliases in preset}
        for entry in self.entries:
            if entry.term in merged:
                for alias in entry.aliases:
                    if alias not in merged[entry.term].aliases:
                        merged[entry.term].aliases.append(alias)
            else:
                merged[entry.term] = entry
        return list(merged.values())

    def apply(self, text: str) -> str:
        if not text:
            return text
        entries = self._active_entries()
        if not entries:
            return text

        # Pass 1: exact alias substring replacement.
        for entry in entries:
            for alias in entry.aliases:
                if alias and alias in text:
                    text = text.replace(alias, entry.term)

        # Pass 2: fuzzy pinyin pass — catches homophone variants not explicitly listed.
        text = self._fuzzy_correct(text, entries)
        return text

    @staticmethod
    def _fuzzy_correct(text: str, entries: list[VocabEntry]) -> str:
        try:
            from pypinyin import lazy_pinyin
        except ImportError:
            return text

        terms = [e.term for e in entries if len(e.term) >= 2]
        if not terms:
            return text

        result = list(text)
        i = 0
        while i < len(result):
            replaced = False
            for term in terms:
                length = len(term)
                if i + length > len(result):
                    continue
                window = "".join(result[i:i + length])
                if window == term:
                    i += length
                    replaced = True
                    break
                if _pinyin_close(window, term):
                    result[i:i + length] = list(term)
                    i += length
                    replaced = True
                    break
            if not replaced:
                i += 1
        return "".join(result)


def _pinyin_close(a: str, b: str) -> bool:
    from pypinyin import lazy_pinyin

    if len(a) != len(b) or a == b:
        return a == b
    pin_a = lazy_pinyin(a)
    pin_b = lazy_pinyin(b)
    if len(pin_a) != len(pin_b):
        return False
    differences = sum(1 for x, y in zip(pin_a, pin_b) if x != y)
    # Allow exactly one differing syllable for terms with 2+ characters — catches a single
    # mis-heard character while staying conservative enough not to over-correct unrelated text.
    return differences <= 1
