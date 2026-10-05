"""Outline-then-fill for the heavy generation stages (secrets, settlement, NPCs, opportunities,
party). One small call lists the stage's items; one call per item writes it in full. Each item
is validated on its own with its own bounded retry; good items are kept even when another
fails; progress lives on the stage row so a rerun resumes at the first unfinished item; the
merged stage is validated once more as a whole.

Why: on GLM-4.5-Air these stages wrote 3–6k tokens in one answer, overran the output budget,
and a single bad entry forced the whole stage to be regenerated (A9 runs, 2026-10-04).
"""

from __future__ import annotations

import json
from typing import Any

from app.worldgen.brief import CampaignBrief
from app.worldgen.envelope import WorldAuthorOut
from app.worldgen.stages import Stage
from app.worldgen.validate import Catalog

KIND = {
    "actors": "actor",
    "locations": "location",
    "mysteries": "mystery",
    "opportunities": "opportunity",
}
ITEM_ATTEMPTS = 2  # one call + one corrective retry per item, never more


def item_label(section: str, x: Any) -> str:
    name = getattr(x, "name", None) or getattr(x, "title", None) or getattr(x, "question", "")
    extra = getattr(x, "occupation", "") or getattr(x, "descriptor", "") or getattr(x, "type", "")
    return f"{x.ref} — {name}" + (f" ({extra})" if extra else "")


def outline_errors(
    stage: Stage,
    items: list[Any],
    catalog: Catalog,
    brief: CampaignBrief,
    notes: list[str],
) -> tuple[list[Any], list[str]]:
    """Check an outline; returns the (possibly trimmed) items and the errors."""
    cfg = stage.itemized
    assert cfg is not None
    kind = KIND[cfg.primary]
    lo, hi = cfg.count
    errors: list[str] = []
    seen: set[str] = set()
    kept = []
    for x in items:
        if not x.ref or x.ref in seen:
            notes.append(f"outline: duplicate or empty ref {x.ref!r} dropped")
            continue
        existing = catalog.kinds.get(x.ref)
        if existing is not None and not (cfg.reuse_existing and existing == kind):
            errors.append(f"outline: ref {x.ref!r} already exists as a {existing}")
            continue
        seen.add(x.ref)
        kept.append(x)
    if len(kept) > hi:
        notes.append(f"outline: {len(kept)} items trimmed to {hi}")
        kept = kept[:hi]
    if stage.key == "party":
        roles = [getattr(x, "role", "npc") for x in kept]
        humans = roles.count("pc_human") + sum(
            1 for r, a in catalog.actors.items() if a.role == "pc_human" and r not in seen
        )
        ais = roles.count("pc_ai") + sum(
            1 for r, a in catalog.actors.items() if a.role == "pc_ai" and r not in seen
        )
        if humans != 1:
            errors.append("outline: the party needs exactly one player character (pc_human)")
        if ais != brief.party_ai_companions:
            errors.append(
                f"outline: the brief asks for {brief.party_ai_companions} companion(s) (pc_ai); "
                f"got {ais}"
            )
        lo = 1 if catalog.imported.get("actors") else lo
    if len(kept) < lo:
        errors.append(f"outline: at least {lo} {cfg.primary} needed; got {len(kept)}")
    return kept, errors


def outline_task(stage: Stage) -> list[str]:
    cfg = stage.itemized
    assert cfg is not None
    lo, hi = cfg.count
    return [
        f"STAGE {stage.key} — OUTLINE. {stage.title}.",
        stage.task,
        f"First step only: LIST the items of this stage in `{cfg.primary}`, {lo} to {hi} of "
        f"them, each with just: {cfg.outline_fields}. Leave every other section out; each item "
        "is written in full in a separate step afterwards.",
    ]


def fill_task(stage: Stage, item: Any, outline: list[Any], guide: str) -> list[str]:
    cfg = stage.itemized
    assert cfg is not None
    others = [item_label(cfg.primary, x) for x in outline if x.ref != item.ref]
    extras = sorted(cfg.fill_sections - {cfg.primary})
    entry = json.dumps(item.model_dump(exclude_defaults=True), ensure_ascii=False)
    return [
        f"STAGE {stage.key} — ITEM {item.ref}. {stage.title}.",
        stage.task,
        f"This step writes ONLY this one item, in full, in `{cfg.primary}` with ref {item.ref}: "
        f"{entry}.",
        "The other items of this stage are written in their own steps; you may refer to them "
        "by ref: " + ("; ".join(others) or "none") + ".",
        (
            f"Also include, for this item only: {', '.join(extras)}."
            if extras
            else "Include nothing else."
        ),
        "Allowed sections: " + guide,
    ]


def merge_filled(order: list[str], filled: dict[str, dict]) -> WorldAuthorOut:
    from app.worldgen.build import combine

    return combine([WorldAuthorOut.model_validate(filled[r]) for r in order if r in filled])


def blame(errors: list[str], order: list[str], filled: dict[str, dict], primary: str) -> dict:
    """Which items to send back after the whole-stage check, each with its errors. An error
    naming an item goes to that item; a shortfall in another section ("needs at least 2
    clues") goes to the items that have none of it (else the last item), so the good items
    are kept and the outline survives. Empty: only a new outline can fix it."""
    out: dict[str, list[str]] = {}
    for e in errors:
        named = [r for r in order if r in e]
        if not named and " needs at least " in e:
            section = e.rsplit(" ", 1)[-1]
            if section != primary:
                named = [r for r in order if not filled.get(r, {}).get(section)] or order[-1:]
                e = f"{e} — add {section} for this item"
        for r in named:
            out.setdefault(r, []).append(e)
    return out


def item_focus(item: Any, outline: list[Any]) -> set[str]:
    """The refs one item's fill is about: itself, its siblings, and every ref its outline
    entry names (its place, its parent, people it is tied to)."""
    refs = {x.ref for x in outline}
    for v in item.model_dump().values():
        if isinstance(v, str) and "_" in v and " " not in v:
            refs.add(v)
        elif isinstance(v, list):
            refs |= {x for x in v if isinstance(x, str) and "_" in x and " " not in x}
    return refs
