from __future__ import annotations


def result_orientation_for_width(width: int, breakpoint: int = 760) -> str:
    return "horizontal" if width >= breakpoint else "vertical"
