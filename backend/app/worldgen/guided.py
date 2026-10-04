"""Guided creation (campaign-generation §2): a short conversation that infers several brief
settings from each natural-language answer, instead of a 100-field form.

Each answer is one bounded `brief_interviewer` call (fast profile). The model proposes a
*patch*; the engine applies only known CampaignBrief fields whose values validate, so a
confused answer can never corrupt the brief. The conversation ends when the model says the
brief is ready, the player says so, or after MAX_TURNS answers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import BriefInterviewOut
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import Campaign
from app.services.memory import MemoryService
from app.services.turns import Turn, budget_from_settings
from app.services.world import CampaignHandle, WorldError
from app.worldgen.brief import CampaignBrief

MAX_TURNS = 8
OPENING_QUESTION = (
    "What kind of story do you want to play? Tell me about the world, the mood, or a "
    "character you have in mind — anything you already know."
)
DONE_WORDS = {"done", "that's it", "thats it", "go", "start", "generate", "ready"}
PROTECTED = {"seed"}  # never set from conversation


@dataclass
class GuidedState:
    turns: list[dict[str, str]] = field(default_factory=list)  # {q, a}
    question: str = OPENING_QUESTION
    done: bool = False
    rejected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns": self.turns,
            "question": self.question,
            "done": self.done,
            "rejected": self.rejected,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> GuidedState:
        d = d or {}
        return cls(
            list(d.get("turns", [])),
            d.get("question", OPENING_QUESTION),
            bool(d.get("done", False)),
            list(d.get("rejected", [])),
        )


def apply_patch(brief: CampaignBrief, patch: dict[str, Any]) -> tuple[CampaignBrief, list[str]]:
    """Apply field by field; anything unknown or invalid is reported and skipped."""
    rejected: list[str] = []
    data = brief.model_dump()
    for k, v in patch.items():
        if k not in CampaignBrief.model_fields or k in PROTECTED:
            rejected.append(f"{k}: not a brief setting")
            continue
        trial = dict(data)
        if k in ("tone",) and isinstance(v, dict):
            trial[k] = {**data.get("tone", {}), **v}
        elif k == "player_character" and isinstance(v, dict):
            trial[k] = {**data.get("player_character", {}), **v}
        else:
            trial[k] = v
        try:
            CampaignBrief.model_validate(trial)
        except ValidationError as exc:
            rejected.append(f"{k}: {exc.errors()[0].get('msg', 'invalid')}")
            continue
        data = trial
    return CampaignBrief.model_validate(data), rejected


class GuidedCreationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        provider,
        embedder=None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.compiler = ContextCompiler(
            session, memory=MemoryService(session, embedder), engine=engine
        )
        self.runner = ModelRunner(session, ModelRouter(settings, provider))

    async def _campaign(self, campaign_id: uuid.UUID) -> Campaign:
        c = await self.session.get(Campaign, campaign_id)
        if c is None:
            raise WorldError("campaign not found")
        if c.status not in ("draft", "generating"):
            raise WorldError("the brief is pre-play only")
        return c

    async def state(self, campaign_id: uuid.UUID) -> tuple[CampaignBrief, GuidedState]:
        c = await self._campaign(campaign_id)
        raw = dict(c.generation_brief or {})
        guided = GuidedState.from_dict(raw.pop("_guided", None))
        return CampaignBrief.model_validate(raw), guided

    async def answer(self, campaign_id: uuid.UUID, message: str) -> dict[str, Any]:
        c = await self._campaign(campaign_id)
        brief, guided = await self.state(campaign_id)
        if guided.done:
            return self._out(brief, guided)
        text = message.strip()
        guided.turns.append({"q": guided.question, "a": text})
        if text.lower().strip(".! ") in DONE_WORDS:
            guided.done = True
            guided.question = ""
            return await self._save(c, brief, guided)
        h = CampaignHandle(c.id, c.active_timeline_id)  # type: ignore[arg-type]
        turn = Turn(h, budget=budget_from_settings(self.settings, None))
        convo = "\n".join(f"Q: {t['q']}\nA: {t['a']}" for t in guided.turns[-6:])
        ctx = await self.compiler.compile(
            h,
            "brief_interviewer",
            actor_id=None,
            purpose="guided campaign creation",
            situation=f'The player just answered: "{text}"',
            extra_sections={
                "brief": brief.model_dump_json(exclude={"seed"}),
                "conversation": convo,
                "task": f"Answer {len(guided.turns)} of at most {MAX_TURNS}. Return the patch "
                "and either one next question or done.",
            },
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call("brief_interviewer", calls=res.calls)
        await turn.finish(self.session)
        if res.ok and isinstance(res.output, BriefInterviewOut):
            brief, rejected = apply_patch(brief, res.output.brief_patch)
            guided.rejected += rejected
            guided.done = res.output.done or not res.output.next_question
            guided.question = "" if guided.done else (res.output.next_question or "")
        else:
            # do less rather than invent: keep the brief, ask the same thing again
            guided.rejected.append(f"interviewer output unusable ({res.status})")
        if len(guided.turns) >= MAX_TURNS and not guided.done:
            guided.done, guided.question = True, ""
        return await self._save(c, brief, guided)

    async def _save(self, c: Campaign, brief: CampaignBrief, guided: GuidedState) -> dict[str, Any]:
        c.generation_brief = {**brief.model_dump(), "_guided": guided.to_dict()}
        c.creation_mode = "guided"
        await self.session.commit()
        return self._out(brief, guided)

    @staticmethod
    def _out(brief: CampaignBrief, guided: GuidedState) -> dict[str, Any]:
        return {
            "question": guided.question or None,
            "done": guided.done,
            "turns": len(guided.turns),
            "brief": brief.model_dump(),
            "rejected": guided.rejected[-5:],
        }
