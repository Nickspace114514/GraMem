"""Transport evidence normalization, shared by live capture and historical linking."""

import re

TRANSPORT = re.compile(
    r"^(?:\[[^\]\n]{1,100}\]\s*)?\[Teams channel thread_id=[^\]\n]+\]\s*\n"
    r"\[Transport context: the thread_id above is already supplied by the Teams bridge\.[^\n]*\]\s*\n"
)


def user_evidence(text):
    if not isinstance(text, str):
        if isinstance(text, list):
            text = "\n".join(
                part.get("text", "")
                for part in text
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            return ""
    return TRANSPORT.sub("", text, count=1).strip()
