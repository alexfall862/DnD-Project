"""Prose-only output for the prose roles (narrator, table assistant).

GLM sometimes answers a prose role with JSON or a fenced block (play session 2: the narrator's
turn-45 output and two table-assistant answers reached the player as raw JSON). The text is
recovered when it is there; structure never reaches the player.
"""

from __future__ import annotations

import json
import re
from typing import Any

FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
TEXT_KEYS = ("narration", "text", "answer", "response", "content", "message", "output")


def _strings(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        for k in TEXT_KEYS:
            if isinstance(x.get(k), str) and x[k].strip():
                return [x[k]]
        out: list[str] = []
        for v in x.values():
            out += _strings(v)
        return out
    if isinstance(x, list):
        out = []
        for v in x:
            out += _strings(v)
        return out
    return []


def _unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s


def prose_only(text: str | None) -> str:
    """The prose in a model's answer: fences removed, a JSON wrapper unwrapped to its text."""
    if not text:
        return ""
    t = text.strip()
    if t.startswith("```"):
        t = FENCE_RE.sub("", t).strip()
    if t[:1] in "{[":
        try:
            data = json.loads(t)
        except ValueError:
            # a truncated object: keep the quoted values that read like sentences
            parts = re.findall(r'"(?:[a-z_]+)"\s*:\s*"((?:[^"\\]|\\.){20,})', t)
            return " ".join(_unescape(p) for p in parts).strip()
        strings = [s.strip() for s in _strings(data) if len(s.strip()) > 1]
        return "\n\n".join(strings).strip()
    return t
