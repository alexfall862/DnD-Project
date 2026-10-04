"""ModelRunner — one audited model call (orchestration §7, §35, §39, §43; ai-contracts §17).

    compiled context → system prompt (role) + user (context + situation) → provider
    → lenient JSON extraction + conveys normalisation + Pydantic validation
    → one bounded repair call on failure (actor roles) → ModelRun (+ DecisionTrace)

The runner never retries beyond the one repair, never guesses missing mechanical state, and
never calls a provider for a context that failed authorization (the compiler raised first).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import CompiledContext
from app.ai.prompts import PromptRepository
from app.ai.providers import ModelRequest, ModelResponse, ProviderError
from app.ai.routing import ModelRouter
from app.ai.validation import validate_output
from app.persistence.models import DecisionTrace, ModelRun
from app.services.world import CampaignHandle

REPAIR_INSTRUCTION = (
    "Your JSON failed validation:\n- {errors}\nReturn the corrected JSON object only."
)
TRUNCATED_INSTRUCTION = (
    "Your previous output was cut off before the JSON ended. Respond again with a much shorter "
    "answer: decision_summary under 25 words, spoken_text under 40 words, at most 2 conveys "
    "items and 1 intention. Return the complete JSON object only."
)


@dataclass
class RunResult:
    model_run_id: uuid.UUID
    status: str  # ok | repaired | invalid | failed
    output: BaseModel | None
    text: str
    structured: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    model_echo: str | None = None
    model_mismatch: bool = False
    calls: int = 1

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "repaired")


@dataclass
class _Pending:
    run_id: uuid.UUID
    ctx: CompiledContext
    req: ModelRequest
    route: Any
    row: ModelRun


class ModelRunner:
    def __init__(
        self, session: AsyncSession, router: ModelRouter, prompts: PromptRepository | None = None
    ) -> None:
        self.session = session
        self.router = router
        self.prompts = prompts or PromptRepository()

    def _request(
        self, ctx: CompiledContext, *, temperature: float | None, run_id: uuid.UUID
    ) -> tuple[ModelRequest, Any, str]:
        route = self.router.resolve(ctx.role.name)
        system, prompt = self.prompts.system_text(ctx.role)
        req = ModelRequest(
            run_id=run_id,
            profile=route.profile,
            model=route.model,
            system=system,
            user=ctx.rendered,
            max_tokens=ctx.role.max_tokens,
            temperature=ctx.role.temperature if temperature is None else temperature,
            json_mode=ctx.role.output_model is not None,
        )
        return req, route, prompt.hash

    async def run(
        self,
        h: CampaignHandle,
        ctx: CompiledContext,
        *,
        turn_id: uuid.UUID | None = None,
        temperature: float | None = None,
    ) -> RunResult:
        pending = await self._begin(h, ctx, turn_id=turn_id, temperature=temperature)
        try:
            resp: ModelResponse | ProviderError = await pending.route.provider.generate(pending.req)
        except ProviderError as exc:
            resp = exc
        return await self._complete(pending, resp)

    async def run_many(
        self,
        h: CampaignHandle,
        ctxs: list[CompiledContext],
        *,
        turn_id: uuid.UUID | None = None,
    ) -> list[RunResult]:
        """Several independent calls from the same snapshot (orchestration §18): rows are
        created and results persisted sequentially on the one session; only the provider
        calls run concurrently (the provider's own semaphore bounds them)."""
        if not ctxs:
            return []
        pendings = [await self._begin(h, c, turn_id=turn_id, temperature=None) for c in ctxs]

        async def gen(p: _Pending) -> ModelResponse | ProviderError:
            try:
                return await p.route.provider.generate(p.req)
            except ProviderError as exc:
                return exc

        responses = await asyncio.gather(*(gen(p) for p in pendings))
        return [await self._complete(p, r) for p, r in zip(pendings, responses, strict=True)]

    async def _begin(
        self,
        h: CampaignHandle,
        ctx: CompiledContext,
        *,
        turn_id: uuid.UUID | None,
        temperature: float | None,
    ) -> _Pending:
        run_id = uuid.uuid4()
        req, route, prompt_hash = self._request(ctx, temperature=temperature, run_id=run_id)
        prompt = self.prompts.get(ctx.role.prompt_id)
        row = ModelRun(
            id=run_id,
            campaign_id=h.campaign_id,
            timeline_id=h.timeline_id,
            turn_id=turn_id,
            provider=route.provider.name,
            profile=route.profile,
            model_requested=route.model,
            role=ctx.role.name,
            actor_id=ctx.actor_id,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            prompt_hash=prompt_hash,
            context_snapshot_id=ctx.snapshot_id,
            parameters={
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
                "json_mode": req.json_mode,
            },
            status="pending",
        )
        self.session.add(row)
        await self.session.flush()
        return _Pending(run_id, ctx, req, route, row)

    async def _complete(self, p: _Pending, first: ModelResponse | ProviderError) -> RunResult:
        ctx, req, route, row, run_id = p.ctx, p.req, p.route, p.row, p.run_id
        calls = 1
        if isinstance(first, ProviderError):
            row.status, row.error, row.ended_at = "failed", str(first), datetime.now(UTC)
            await self.session.flush()
            return RunResult(run_id, "failed", None, "", errors=[str(first)], calls=calls)
        resp = first
        text, structured, output, errors = resp.text, None, None, []
        if ctx.role.output_model is not None:
            output, structured, errors = validate_output(
                text, ctx.role.output_model, belief_ids=ctx.belief_refs, fact_ids=ctx.fact_refs
            )
            if output is None and ctx.role.repair:
                calls += 1
                truncated = resp.finish_reason == "length"
                instruction = (
                    TRUNCATED_INSTRUCTION
                    if truncated
                    else REPAIR_INSTRUCTION.format(errors="\n- ".join(errors))
                )
                req.history = [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": instruction},
                ]
                req.temperature = 0.1
                try:
                    resp2 = await route.provider.generate(req)
                except ProviderError as exc:
                    resp2 = None
                    errors = errors + [f"repair failed: {exc}"]
                if resp2 is not None:
                    text2 = resp2.text
                    output, structured, errors2 = validate_output(
                        text2,
                        ctx.role.output_model,
                        belief_ids=ctx.belief_refs,
                        fact_ids=ctx.fact_refs,
                    )
                    resp = _merge(resp, resp2)
                    text = text2
                    errors = errors2 if output is not None else errors + errors2
        status = (
            "ok"
            if (output is not None and calls == 1) or (ctx.role.output_model is None)
            else "repaired"
            if output is not None
            else "invalid"
        )
        row.raw_output, row.structured_output, row.validation = (
            text,
            structured,
            {
                "errors": errors,
                "calls": calls,
                "model_mismatch": resp.model_mismatch,
                "finish_reason": resp.finish_reason,
            },
        )
        row.status, row.model_echo, row.latency_ms = status, resp.model_echo, resp.latency_ms
        row.prompt_tokens, row.completion_tokens, row.cached_tokens, row.ended_at = (
            resp.prompt_tokens,
            resp.completion_tokens,
            resp.cached_tokens,
            datetime.now(UTC),
        )
        if resp.model_mismatch:
            row.error = f"model echo {resp.model_echo!r} != requested {route.model!r}"
        if output is not None and ctx.actor_id is not None and hasattr(output, "decision_summary"):
            self.session.add(
                DecisionTrace(
                    model_run_id=run_id,
                    actor_id=ctx.actor_id,
                    decision_summary=getattr(output, "decision_summary", ""),
                    relevant_beliefs=[i.source_id for i in ctx.items if i.section == "beliefs"],
                    relevant_memories=[
                        i.source_id for i in ctx.items if i.section in ("memories", "core_memories")
                    ],
                    relationships=[
                        i.source_id for i in ctx.items if i.section == "relationships_own"
                    ],
                    mechanics={"sections": sorted(ctx.sections)},
                    selected_intent={
                        "intentions": [it.model_dump() for it in getattr(output, "intentions", [])]
                    }
                    if hasattr(output, "intentions")
                    else {},
                )
            )
        await self.session.flush()
        return RunResult(
            run_id,
            status,
            output,
            text,
            structured,
            errors,
            resp.latency_ms,
            resp.prompt_tokens,
            resp.completion_tokens,
            resp.cached_tokens,
            resp.model_echo,
            resp.model_mismatch,
            calls,
        )

    async def stream(
        self, h: CampaignHandle, ctx: CompiledContext, *, turn_id: uuid.UUID | None = None
    ) -> AsyncIterator[str | RunResult]:
        """Yield text deltas, then a final RunResult. Used by the narrator (prose roles)."""
        run_id = uuid.uuid4()
        req, route, prompt_hash = self._request(ctx, temperature=None, run_id=run_id)
        req.json_mode = ctx.role.output_model is not None
        prompt = self.prompts.get(ctx.role.prompt_id)
        row = ModelRun(
            id=run_id,
            campaign_id=h.campaign_id,
            timeline_id=h.timeline_id,
            turn_id=turn_id,
            provider=route.provider.name,
            profile=route.profile,
            model_requested=route.model,
            role=ctx.role.name,
            actor_id=ctx.actor_id,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            prompt_hash=prompt_hash,
            context_snapshot_id=ctx.snapshot_id,
            parameters={
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
                "stream": True,
            },
            status="pending",
        )
        self.session.add(row)
        await self.session.flush()
        started = datetime.now(UTC)
        chunks: list[str] = []
        try:
            async for delta in route.provider.stream(req):
                chunks.append(delta)
                yield delta
        except ProviderError as exc:
            row.status, row.error, row.ended_at = "failed", str(exc), datetime.now(UTC)
            await self.session.flush()
            yield RunResult(run_id, "failed", None, "".join(chunks), errors=[str(exc)])
            return
        text = "".join(chunks)
        output, structured, errors = (None, None, [])
        if ctx.role.output_model is not None:
            output, structured, errors = validate_output(text, ctx.role.output_model)
        row.raw_output, row.structured_output, row.validation = (
            text,
            structured,
            {"errors": errors, "calls": 1},
        )
        row.status = "ok" if (output is not None or ctx.role.output_model is None) else "invalid"
        row.latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        row.ended_at = datetime.now(UTC)
        await self.session.flush()
        yield RunResult(run_id, row.status, output, text, structured, errors, row.latency_ms or 0)


def _merge(a: ModelResponse, b: ModelResponse) -> ModelResponse:
    return ModelResponse(
        text=b.text,
        model_echo=b.model_echo or a.model_echo,
        latency_ms=a.latency_ms + b.latency_ms,
        prompt_tokens=(a.prompt_tokens or 0) + (b.prompt_tokens or 0),
        completion_tokens=(a.completion_tokens or 0) + (b.completion_tokens or 0),
        cached_tokens=(a.cached_tokens or 0) + (b.cached_tokens or 0),
        model_mismatch=a.model_mismatch or b.model_mismatch,
        raw=b.raw,
    )
