"""What has happened in the current scene, as the focus player saw it (play session
2026-10-05: the narrator only saw the current turn, so a deal made two turns earlier read as
new; extras promoted to living characters need to remember what they witnessed).

Built from `player_turns` (the feed: exactly what the API returned to this player), so it
never contains anything the focus player did not see. Callers that hand it to someone else
(a promoted NPC) drop private channels the other person could not have heard.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import Event, PlayerTurn, Scene

PRIVATE_CHANNELS = {"whisper", "private", "ooc"}


async def scene_turns(
    session: AsyncSession, focus_actor_id: uuid.UUID, scene: Scene | None, *, limit: int = 8
) -> list[PlayerTurn]:
    """The focus player's most recent turns in this scene, oldest first."""
    q = select(PlayerTurn).where(PlayerTurn.actor_id == focus_actor_id)
    if scene is not None and scene.start_event_id is not None:
        started = await session.get(Event, scene.start_event_id)
        if started is not None:
            q = q.where(PlayerTurn.created_at >= started.created_at)
    rows = (
        (await session.execute(q.order_by(PlayerTurn.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return list(reversed(rows))


def render_turns(
    turns: list[PlayerTurn],
    *,
    player_name: str,
    names: dict[str, str],
    public_only: bool = False,
    narration_chars: int = 360,
) -> list[str]:
    """One compact paragraph per turn: what the player did, who said what, what was narrated.
    `names` maps actor ids to display names; `public_only` drops whispers, private thoughts
    and OOC (for a listener who was not addressed)."""
    out: list[str] = []
    for t in turns:
        r: dict[str, Any] = t.result or {}
        if r.get("error") or r.get("clarification"):
            continue
        ch = t.channel or "auto"
        actual = r.get("channel") or ch
        if public_only and (ch in PRIVATE_CHANNELS or actual in PRIVATE_CHANNELS):
            continue
        if ch == "ooc" or actual == "ooc":
            continue
        verb = {"whisper": "whispered", "private": "thought"}.get(actual, "did/said")
        parts = [f"{player_name} {verb}: {t.input_text.strip()[:300]}"]
        for sp in r.get("speakers", []) or []:
            if not sp.get("text") or str(sp.get("actor_id")) == "":
                continue
            who = names.get(str(sp.get("actor_id")), "someone")
            if who == player_name:
                continue
            parts.append(f'{who}: "{sp["text"][:200]}"')
        outcomes = [
            f"{str(a.get('action', '')).split('.')[-1]} {a.get('status')}"
            for a in r.get("actions", []) or []
        ]
        if outcomes:
            parts.append("outcome: " + ", ".join(outcomes))
        narr = (r.get("narration") or "").strip()
        if narr:
            parts.append(
                "narrated: "
                + (narr[:narration_chars] + ("…" if len(narr) > narration_chars else ""))
            )
        out.append(" | ".join(parts))
    return out
