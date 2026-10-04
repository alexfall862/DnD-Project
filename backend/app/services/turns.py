"""Turn budget, degradation ladder and telemetry (turn-budget-and-latency.md §3, §5, §7;
Invariant 17). Applies from the first orchestrator commit.

A `Turn` is opened per player input, every model call is recorded against it, the ladder
decides which optional work to drop when time is at risk, and `finish()` writes the
`turn_metrics` row whether the turn succeeded, failed or needed clarification.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.persistence.models import TurnMetrics
from app.services.world import CampaignHandle

# Defaults from the spec (revised 2026-10-03); campaign settings may override.
DEFAULT_BUDGET = {
    "first_output_ms": 2000,
    "first_output_hard_ms": 5000,
    "first_narration_simple_ms": 12000,
    "first_narration_complex_ms": 25000,
    "first_narration_hard_ms": 40000,
    "combat_round_ms": 40000,
    "sync_calls": 4,
    "sync_calls_hard": 6,
    "background_calls": 3,
    "visible_reactions": 2,
}

LADDER = (
    "drop_canon_extractor",
    "defer_memory_processing",
    "reduce_visible_reactions_to_1",
    "use_fallback_policy_in_combat",
    "short_narrator_prompt",
    "skip_narrator",
)


@dataclass
class Turn:
    h: CampaignHandle
    turn_id: uuid.UUID = field(default_factory=uuid.uuid4)
    started: float = field(default_factory=time.perf_counter)
    budget: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BUDGET))
    sync_calls: int = 0
    background_calls: int = 0
    calls_by_role: dict[str, int] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    max_context_tokens: int = 0
    ms_to_first_output: int | None = None
    ms_to_first_narration: int | None = None
    degradation_steps: list[str] = field(default_factory=list)
    budget_breached: bool = False
    claim_extractor_invoked: int = 0
    belief_processor_scheduled: int = 0
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # per-turn facts for the response
    inapplicable: set[str] = field(default_factory=set)  # ladder steps that cannot apply

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def mark_first_output(self) -> None:
        if self.ms_to_first_output is None:
            self.ms_to_first_output = self.elapsed_ms

    def mark_first_narration(self) -> None:
        if self.ms_to_first_narration is None:
            self.ms_to_first_narration = self.elapsed_ms

    def record_call(
        self,
        role: str,
        *,
        sync: bool = True,
        calls: int = 1,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        context_tokens: int | None = None,
    ) -> None:
        if sync:
            self.sync_calls += calls
        else:
            self.background_calls += calls
        self.calls_by_role[role] = self.calls_by_role.get(role, 0) + calls
        self.prompt_tokens += prompt_tokens or 0
        self.completion_tokens += completion_tokens or 0
        if context_tokens:
            self.max_context_tokens = max(self.max_context_tokens, context_tokens)
        if self.sync_calls > self.budget["sync_calls_hard"]:
            self.budget_breached = True

    def can_make_sync_call(self) -> bool:
        """Hard cap: beyond it optional calls are aborted and the breach logged."""
        if self.sync_calls >= self.budget["sync_calls_hard"]:
            self.budget_breached = True
            self.notes.append("sync call cap reached")
            return False
        return True

    def at_risk(self, *, complex_turn: bool) -> bool:
        target = self.budget[
            "first_narration_complex_ms" if complex_turn else "first_narration_simple_ms"
        ]
        return self.elapsed_ms > target * 0.7 or self.sync_calls >= self.budget["sync_calls"]

    def degrade(self) -> str | None:
        """Take the next ladder step not yet taken; returns it (or None when exhausted)."""
        for step in LADDER:
            if step not in self.degradation_steps and step not in self.inapplicable:
                self.degradation_steps.append(step)
                return step
        return None

    def degraded(self, step: str) -> bool:
        return step in self.degradation_steps

    async def finish(
        self, session: AsyncSession, *, extra: dict[str, Any] | None = None
    ) -> TurnMetrics:
        row = TurnMetrics(
            campaign_id=self.h.campaign_id,
            timeline_id=self.h.timeline_id,
            turn_id=self.turn_id,
            wall_ms_total=self.elapsed_ms,
            ms_to_first_output=self.ms_to_first_output,
            ms_to_first_narration_token=self.ms_to_first_narration,
            sync_model_calls=self.sync_calls,
            background_model_calls=self.background_calls,
            calls_by_role=dict(self.calls_by_role),
            prompt_tokens_total=self.prompt_tokens,
            completion_tokens_total=self.completion_tokens,
            max_context_tokens=self.max_context_tokens,
            degradation_steps=list(self.degradation_steps),
            budget_breached=self.budget_breached
            or self.elapsed_ms > self.budget["first_narration_hard_ms"],
            claim_extractor_invoked=self.claim_extractor_invoked,
            belief_processor_scheduled=self.belief_processor_scheduled,
        )
        session.add(row)
        await session.flush()
        return row

    def summary(self) -> dict[str, Any]:
        return {
            "turn_id": str(self.turn_id),
            "wall_ms_total": self.elapsed_ms,
            "ms_to_first_output": self.ms_to_first_output,
            "ms_to_first_narration_token": self.ms_to_first_narration,
            "sync_model_calls": self.sync_calls,
            "background_model_calls": self.background_calls,
            "calls_by_role": dict(self.calls_by_role),
            "degradation_steps": list(self.degradation_steps),
            "budget_breached": self.budget_breached
            or self.elapsed_ms > self.budget["first_narration_hard_ms"],
            "claim_extractor_invoked": self.claim_extractor_invoked,
            "belief_processor_scheduled": self.belief_processor_scheduled,
            "notes": list(self.notes),
            **self.extra,
        }


def budget_from_settings(
    settings: Settings, campaign_settings: dict[str, Any] | None = None
) -> dict[str, int]:
    b = dict(DEFAULT_BUDGET)
    b["sync_calls"] = settings.max_sync_model_calls_per_turn
    b["sync_calls_hard"] = settings.hard_cap_sync_model_calls_per_turn
    b["visible_reactions"] = settings.spotlight_visible_reactions
    for k, v in (campaign_settings or {}).get("latency_budget", {}).items():
        if k in b:
            b[k] = int(v)
    if (campaign_settings or {}).get("spotlight_visible_reactions") is not None:
        b["visible_reactions"] = int(campaign_settings["spotlight_visible_reactions"])
    return b
