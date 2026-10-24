"""Exact counts for the selected tokenizer; UTF-8 upper bound if unavailable."""

import json

try:
    import tiktoken

    _codec = tiktoken.get_encoding("cl100k_base")
except (ImportError, OSError, ValueError):
    _codec = None


def count(text: str) -> int:
    return len(_codec.encode(text, disallowed_special=())) if _codec else len(text.encode("utf-8"))


def limit(text: str, budget: int) -> str:
    if count(text) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
