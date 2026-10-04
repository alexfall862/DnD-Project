"""Structured-output extraction, normalisation and validation (ai-contracts §17, §21;
DECISIONS.md 04b findings 3–4).

- lenient JSON extraction (GLM wraps json_object output in a code fence);
- `conveys[]` normalisation: a stray top-level `predicate`/`value`/`subject_entity_id`/
  `object_entity_id` is moved into `proposition`; `kind` is advisory and is corrected from the
  id family (`b_`/belief uuid → belief_ref, `f_`/fact → fact_ref);
- Pydantic validation against the role's output model;
- a readable error list for the one bounded repair call.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
PROP_FIELDS = ("subject_entity_id", "predicate", "object_entity_id", "value")


def extract_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates = [text.strip()]
    m = FENCE.search(text)
    if m:
        candidates.insert(0, m.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    err = None
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError as e:
            err = str(e)
            continue
        if isinstance(obj, dict):
            return obj, None
        err = "top-level JSON is not an object"
    return None, err


def normalize_conveys(
    obj: dict[str, Any], *, belief_ids: set[str] = frozenset(), fact_ids: set[str] = frozenset()
) -> dict[str, Any]:
    items = obj.get("conveys")
    if not isinstance(items, list):
        return obj
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        it = dict(it)
        stray = {k: it.pop(k) for k in PROP_FIELDS if k in it}
        if stray:
            prop = it.get("proposition") if isinstance(it.get("proposition"), dict) else {}
            it["proposition"] = {**stray, **prop}
        ref = it.get("ref_id")
        if ref:
            if ref in belief_ids or str(ref).startswith("b_"):
                it["kind"] = "belief_ref"
            elif ref in fact_ids or str(ref).startswith("f_"):
                it["kind"] = "fact_ref"
        elif it.get("kind") in ("belief_ref", "fact_ref"):
            it["kind"] = "proposition"
        it.setdefault("stance", "asserts_true")
        it.setdefault("fidelity", "full")
        it.setdefault("about_speaker_self", False)
        out.append(it)
    obj["conveys"] = out
    return obj


def errors_of(exc: ValidationError) -> list[str]:
    out = []
    for e in exc.errors()[:8]:
        loc = "/".join(str(p) for p in e.get("loc", ())) or "<root>"
        out.append(f"{loc}: {e.get('msg')}")
    return out


def validate_output(
    text: str,
    model: type[BaseModel],
    *,
    belief_ids: set[str] = frozenset(),
    fact_ids: set[str] = frozenset(),
) -> tuple[BaseModel | None, dict[str, Any] | None, list[str]]:
    """Returns (validated model, normalised dict, errors)."""
    obj, err = extract_json(text)
    if obj is None:
        return None, None, [f"json: {err}"]
    obj = normalize_conveys(obj, belief_ids=belief_ids, fact_ids=fact_ids)
    try:
        return model.model_validate(obj), obj, []
    except ValidationError as exc:
        return None, obj, errors_of(exc)


def _boundary(stack: list[str]) -> bool:
    """A cut is safe only between the elements of a top-level list (actors, facts, ...) or
    between top-level fields — never inside an item, which would keep it half-written."""
    return len(stack) == 1 or (len(stack) == 2 and stack[-1] == "]")


def salvage_truncated_json(text: str) -> str | None:
    """A cut-off JSON object closed at the last *complete* value: every item that was fully
    written is kept, the incomplete tail is dropped, nothing is invented. Returns the repaired
    text or None. Used only for list-shaped roles (A9 generation runs: the NPC stage overran its
    output budget and the repair turn timed out on the server)."""
    start = text.find("{")
    if start < 0:
        return None
    body = text[start:]
    stack: list[str] = []
    in_str = esc = False
    last_good: tuple[int, list[str]] | None = None
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
            if not stack:
                return body[: i + 1]  # it was complete after all
            if _boundary(stack):
                last_good = (i + 1, list(stack))
        elif ch == "," and _boundary(stack):
            last_good = (i, list(stack))
    if last_good is None:
        return None
    cut, open_ = last_good
    candidate = body[:cut].rstrip().rstrip(",") + "".join(reversed(open_))
    try:
        json.loads(candidate)
    except ValueError:
        return None
    return candidate
