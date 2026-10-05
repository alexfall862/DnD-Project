"""GenerationService — staged campaign generation (campaign-generation §5, §25–§26;
orchestration §27–§28; api-contracts §6).

    create_run(campaign, brief) → run(run) → [regenerate(stage, guidance)]* → start(campaign)

Each stage is one bounded World Author call (plus at most one corrective retry with the
validation errors), compiled from the brief, the accepted earlier stages and the ruleset's
public capabilities. A stage's output is accepted only if `validate_stage` passes; nothing is
built until `start`, which builds the world in one unit of work, runs the quality checks and
either activates the campaign or rolls everything back.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.domain import events as ev
from app.engine.core import RULESETS_DIR, RulesEngine
from app.engine.effects import REGISTRY
from app.engine.ruleset import modules_for_genres
from app.persistence.models import Campaign
from app.persistence.models.generation import GenerationRun, GenerationStage
from app.services.events import EventTransaction, unit_of_work
from app.services.memory import MemoryService
from app.services.turns import Turn, budget_from_settings
from app.services.world import CampaignHandle, WorldError
from app.worldgen.brief import CampaignBrief
from app.worldgen.build import WorldBuilder, combine
from app.worldgen.envelope import WorldAuthorOut
from app.worldgen.itemized import (
    ITEM_ATTEMPTS,
    KIND,
    blame,
    fill_task,
    item_focus,
    merge_filled,
    outline_errors,
    outline_task,
)
from app.worldgen.quality import quality_errors
from app.worldgen.stages import STAGE_BY_KEY, STAGES, Stage, dependents
from app.worldgen.validate import Catalog, final_errors, validate_stage

MAX_ATTEMPTS = 2  # one call + one corrective retry: never "ask again until solved"

FIELD_GUIDE = {
    "facts": "facts: [{key, predicate (a full statement), subject_ref?, object_ref?, value?, "
    "sensitivity public|private|secret, canon latent|established, known_by_refs[], era?}] — "
    "subject_ref/object_ref only for refs that exist (listed or defined in this answer); "
    "otherwise leave them out and say it in the predicate; known_by_refs only for existing "
    "actor refs (before people exist, leave it empty)",
    "locations": "locations: [{ref, name, type, parent_ref?, detail outline|latent|materialized, "
    "descriptor, features[], zones[{key, name, cover none|light|heavy, exit, features[]}], "
    "adjacency[[zoneA, zoneB]], entry_zone?, simulation_state{}, settlement bool}]",
    "routes": "routes: [{from_ref, to_ref, travel_minutes}]",
    "cultures": "cultures: [{ref, name, homeland_ref?, values[], languages[], customs, "
    "internal_variation}]",
    "factions": "factions: [{ref, name, kind polity|faction, scope world|local, description, "
    "public, ideology, resources{}, territory_refs[], allies[], rivals[], public_goal, "
    "hidden_goal, plan_steps[{title, at_day?, kind deterministic|decision}], "
    "simulation_priority}]",
    "actors": "actors: [{ref, name, role npc|pc_human|pc_ai, importance "
    "full|important|standard|background, descriptor, occupation, location_ref, alive, "
    "attributes{might, agility, intellect, presence, resolve}, skills{name: rank}, traits[], "
    "equipment[{name, template_key}], summary, dimensions{risk_tolerance, aggression, empathy, "
    "curiosity, loyalty, impulsiveness, honesty, sociability, ambition}, goals[{description, "
    "priority, target_refs[]}], beliefs[{predicate, subject_ref?, object_ref?, type, "
    "confidence}], knows_fact_keys[], knows_refs[], core_memories[], relationships[{target_ref, "
    "trust, respect, affection, fear, resentment, familiarity}], faction_refs[], "
    "leads_faction_ref?, culture_ref?}]",
    "conflicts": "conflicts: [{ref, title, participant_refs[], stakes, status, escalation, scale}]",
    "pressures": "pressures: [{ref, title, kind, source_refs[], clock[{title, at_day}]}]",
    "mysteries": "mysteries: [{ref, question, truth_fact_keys[], participant_refs[], "
    "timeline[], red_herring_fact_keys[]}]",
    "clues": "clues: [{ref, mystery_ref, clue_type physical|document|social, "
    "supports_fact_key, entity_ref? (item), destructible, reliability}]",
    "items": "items: [{ref, name, template_key, location_ref?, zone?, holder_ref?, concealed, "
    "concealment_difficulty?, public{}, hidden{}, document?{text, author_ref?, "
    "conveys_fact_keys[], conveys_propositions[], names_refs[]}, mechanics_key?}]",
    "mechanics": "mechanics: [{key, name, tier low|minor, description, passive?{type, params}, "
    "activated?{type, params}}]; item effect types and their params: modify_check{check "
    "'check.*', op add|subtract|advantage|disadvantage, amount -3..3}, modify_resource{resource, "
    "amount}, restore_resource{resource, amount}, deal_damage{amount 1d4..1d8, damage_type}, "
    "apply_condition{condition, intensity?}, remove_condition{condition}, "
    "grant_capability{capability: a short snake_case tag, e.g. sense_echoes}; any effect "
    "may add duration_seconds, uses_per_day, when",
    "opportunities": "opportunities: [{ref, title, pressure_ref?, routes[{kind, via_ref?, "
    "detail}] (at least two)}]",
    "schedules": "schedules: [{key, at_day, type fact.establish|clue.destroy|location.state|"
    "actor.travel|decision, fact_key?, clue_ref?, location_ref?, actor_ref?, faction_ref?, "
    "question?, patch{}}]",
    "opening": "opening: {location_ref, hour, weather, situation, present_refs[], "
    "positions{actor_ref: zone}}",
}


@dataclass
class StartResult:
    campaign_id: uuid.UUID
    opening_scene_id: uuid.UUID
    player_actor_id: uuid.UUID
    party_id: uuid.UUID | None

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) if v else None for k, v in self.__dict__.items()}


class GenerationService:
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
        self.engine = engine
        self.memory = MemoryService(session, embedder)
        self.compiler = ContextCompiler(session, memory=self.memory, engine=engine)
        self.runner = ModelRunner(session, ModelRouter(settings, provider))

    # -- runs ----------------------------------------------------------------------------------

    async def create_run(
        self, campaign_id: uuid.UUID, brief: CampaignBrief, *, scope: str = "full"
    ) -> GenerationRun:
        campaign = await self.session.get(Campaign, campaign_id)
        if campaign is None:
            raise WorldError("campaign not found")
        if campaign.status not in ("draft", "generating"):
            raise WorldError("generation is pre-play only (campaign is not a draft)")
        campaign.generation_brief = brief.model_dump()
        campaign.status = "generating"
        campaign.campaign_mode = brief.campaign_mode
        # genre modules (campaign-generation §4): chosen once, from the brief, before any stage
        modules = modules_for_genres(RULESETS_DIR / campaign.ruleset_key, brief.genres)
        campaign.settings = {**(campaign.settings or {}), "genre_modules": modules}
        previous = await self.latest_run(campaign_id)
        carried = None
        if previous is not None:
            carried = next(
                (
                    s
                    for s in await self.stages(previous.id)
                    if s.stage_key == "import" and s.status == "ready"
                ),
                None,
            )
        run = GenerationRun(campaign_id=campaign_id, brief=brief.model_dump(), scope=scope)
        self.session.add(run)
        await self.session.flush()
        if carried is not None:  # an imported world survives starting a new run
            self.session.add(
                GenerationStage(
                    run_id=run.id,
                    stage_key="import",
                    order_index=-1,
                    status="ready",
                    output=carried.output,
                    errors=[],
                    attempts=carried.attempts,
                )
            )
        for i, st in enumerate(STAGES):
            self.session.add(
                GenerationStage(
                    run_id=run.id,
                    stage_key=st.key,
                    order_index=i,
                    status="pending",
                    depends_on=list(st.depends_on),
                )
            )
        await self.session.commit()
        return run

    async def stages(self, run_id: uuid.UUID) -> list[GenerationStage]:
        return list(
            (
                await self.session.execute(
                    select(GenerationStage)
                    .where(GenerationStage.run_id == run_id)
                    .order_by(GenerationStage.order_index)
                )
            )
            .scalars()
            .all()
        )

    async def catalog(self, run_id: uuid.UUID, *, upto: str | None = None) -> Catalog:
        envs = []
        for st in await self.stages(run_id):
            if upto is not None and st.stage_key == upto:
                break
            if st.status == "ready" and st.output is not None:
                envs.append((st.stage_key, WorldAuthorOut.model_validate(st.output)))
        return Catalog.build(envs)

    async def run(self, run_id: uuid.UUID, *, max_stages: int | None = None) -> GenerationRun:
        """Run every pending/invalidated stage in order. Stops at the first stage that cannot
        be accepted (its errors are on the stage row)."""
        run = await self._run(run_id)
        run.status = "running"
        done = 0
        for st in await self.stages(run_id):
            if st.status == "ready":
                continue
            if max_stages is not None and done >= max_stages:
                break
            ok = await self._stage(run, st)
            done += 1
            if not ok:
                run.status = "failed"
                run.error = f"stage {st.stage_key} failed: {'; '.join(st.errors[:5])}"
                await self.session.commit()
                return run
        remaining = [s for s in await self.stages(run_id) if s.status != "ready"]
        run.status = "ready" if not remaining else "running"
        run.error = None
        await self.session.commit()
        return run

    async def regenerate(
        self, run_id: uuid.UUID, stage_key: str, *, guidance: str | None = None
    ) -> list[str]:
        """Pre-play reroll (§26): only dependent material is invalidated. The stage is
        regenerated now; its dependents are regenerated by the next `run`."""
        run = await self._run(run_id)
        campaign = await self.session.get(Campaign, run.campaign_id)
        if campaign is None or campaign.status not in ("draft", "generating"):
            raise WorldError("regeneration is pre-play only; established canon cannot change")
        if stage_key == "import":
            raise WorldError("an import is replaced by importing again, not regenerated")
        if stage_key not in STAGE_BY_KEY:
            raise WorldError(f"unknown stage {stage_key!r}")
        rows = {s.stage_key: s for s in await self.stages(run_id)}
        invalidated = dependents(stage_key)
        for k in invalidated:
            row = rows[k]
            if row.status != "pending":
                row.status, row.output = "invalidated", None
            row.progress = {}
        target = rows[stage_key]
        target.status, target.output, target.guidance = "pending", None, guidance
        target.progress = {}
        target.attempts = 0
        await self.session.flush()
        ok = await self._stage(run, target)
        run.status = "running" if ok else "failed"
        await self.session.commit()
        return invalidated

    async def _run(self, run_id: uuid.UUID) -> GenerationRun:
        run = await self.session.get(GenerationRun, run_id)
        if run is None:
            raise WorldError("generation run not found")
        return run

    # -- one stage -----------------------------------------------------------------------------

    async def rules_for(self, campaign_id: uuid.UUID) -> RulesEngine:
        c = await self.session.get(Campaign, campaign_id)
        if c is None or not (c.settings or {}).get("genre_modules"):
            return self.engine
        return RulesEngine.for_campaign(c.ruleset_key, c.settings)

    async def _ask(self, h, turn: Turn, stage: Stage, sections: dict[str, str], what: str):
        ctx = await self.compiler.compile(
            h,
            "world_author",
            actor_id=None,
            purpose=f"generation stage {stage.key} {what}".strip(),
            situation=f"Generate stage: {stage.key} ({stage.title}) {what}. Return only JSON.",
            extra_sections=sections,
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "world_author",
            sync=False,
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        return res

    async def _stage(self, run: GenerationRun, row: GenerationStage) -> bool:
        stage = STAGE_BY_KEY[row.stage_key]
        if stage.itemized is not None:
            return await self._itemized_stage(run, row, stage)
        rules = await self.rules_for(run.campaign_id)
        brief = CampaignBrief.model_validate(run.brief)
        catalog = await self.catalog(run.id, upto=row.stage_key)
        h = await self._handle(run.campaign_id)
        turn = Turn(h, budget=budget_from_settings(self.settings, None))
        row.status = "running"
        errors: list[str] = []
        partial: WorldAuthorOut | None = None  # a salvaged, incomplete answer to continue
        for attempt in range(1, MAX_ATTEMPTS + 1):
            row.attempts = attempt
            continuing = partial is not None
            res = await self._ask(
                h,
                turn,
                stage,
                self._sections(
                    stage, brief, catalog, row.guidance, errors, rules=rules, partial=partial
                ),
                "",
            )
            row.model_run_id = res.model_run_id
            if not res.ok or not isinstance(res.output, WorldAuthorOut):
                errors = [f"output unusable: {res.status} {'; '.join(res.errors)[:300]}"]
                continue
            env: WorldAuthorOut = res.output
            if continuing:
                # the continuation adds to what the cut-off answer already holds
                env = combine([partial, env])  # type: ignore[list-item]
            notes: list[str] = []
            if continuing:
                notes.append("continued after a cut-off answer; both parts combined")
            if res.status == "salvaged":
                notes.append("the answer was cut off; its complete items were kept")
            errors = validate_stage(
                stage, env, catalog, ruleset=rules.ruleset, brief=brief, notes=notes
            )
            if not errors and stage.key == STAGES[-1].key:
                # whole-world checks once the last stage is in
                trial = await self.catalog(run.id, upto=stage.key)
                trial.add(stage.key, env)
                errors = final_errors(trial)
            if errors and res.status == "salvaged" and not continuing:
                partial = env  # ask for the missing part instead of starting over
            if not errors:
                row.output = env.model_dump()
                row.status = "ready"
                row.errors = [f"note: {n}" for n in notes]  # what was normalized, for review
                await turn.finish(self.session)
                await self.session.flush()
                return True
        row.status = "failed"
        row.errors = errors
        await turn.finish(self.session)
        await self.session.flush()
        return False

    # -- itemized stages: outline, then one call per item (app/worldgen/itemized.py) ----------

    async def _save_progress(self, row: GenerationStage, prog: dict) -> None:
        row.progress = copy.deepcopy(prog)  # a new object, so the JSONB change is flushed
        await self.session.commit()  # survives a crash: a rerun resumes from here

    async def _itemized_stage(self, run: GenerationRun, row: GenerationStage, stage: Stage) -> bool:
        cfg = stage.itemized
        assert cfg is not None
        rules = await self.rules_for(run.campaign_id)
        brief = CampaignBrief.model_validate(run.brief)
        base = await self.catalog(run.id, upto=row.stage_key)
        h = await self._handle(run.campaign_id)
        turn = Turn(h, budget=budget_from_settings(self.settings, None))
        row.status = "running"
        prog: dict[str, Any] = copy.deepcopy(row.progress or {})
        calls = 0

        async def fail(errors: list[str]) -> bool:
            row.status, row.errors, row.attempts = "failed", errors, calls
            await turn.finish(self.session)
            await self.session.flush()
            return False

        # 1. the outline (kept across reruns once accepted)
        errors: list[str] = []
        if not prog.get("outline"):
            outline = None
            for _ in range(ITEM_ATTEMPTS):
                calls += 1
                res = await self._ask(
                    h,
                    turn,
                    stage,
                    self._sections(
                        stage,
                        brief,
                        base,
                        row.guidance,
                        errors,
                        rules=rules,
                        head=outline_task(stage),
                    ),
                    "outline",
                )
                row.model_run_id = res.model_run_id
                if not res.ok or not isinstance(res.output, WorldAuthorOut):
                    errors = [f"output unusable: {res.status} {'; '.join(res.errors)[:300]}"]
                    continue
                onotes: list[str] = []
                items, errors = outline_errors(
                    stage, getattr(res.output, cfg.primary), base, brief, onotes
                )
                if not errors:
                    outline = items
                    prog = {
                        "outline": [x.model_dump(exclude_defaults=True) for x in items],
                        "filled": {},
                        "failed": [],
                        "item_errors": {},
                        "notes": onotes,
                    }
                    break
            if outline is None:
                return await fail(errors)
            await self._save_progress(row, prog)

        items = getattr(WorldAuthorOut.model_validate({cfg.primary: prog["outline"]}), cfg.primary)
        order = [x.ref for x in items]
        guide = "; ".join(FIELD_GUIDE[sec] for sec in sorted(cfg.fill_sections))

        for _round in range(2):  # fills, then at most one repair round after the whole check
            # 2. one call per unfinished item; good items are kept whatever happens to others
            prog["failed"] = []
            for item in items:
                if item.ref in prog["filled"]:
                    continue
                env, inotes, errs, used = await self._fill_item(
                    h, turn, row, stage, item, items, base, prog, brief, rules, guide
                )
                calls += used
                if env is None:
                    prog["failed"].append(item.ref)
                    prog["item_errors"][item.ref] = errs
                else:
                    prog["filled"][item.ref] = env.model_dump()
                    prog["item_errors"].pop(item.ref, None)
                    prog["notes"] += [f"{item.ref}: {n}" for n in inotes]
                await self._save_progress(row, prog)
            if prog["failed"]:
                return await fail(
                    [
                        f"item {r}: {e}"
                        for r in prog["failed"]
                        for e in prog["item_errors"].get(r, [])[:4]
                    ]
                    + [
                        f"note: kept {len(prog['filled'])} finished item(s); a rerun retries "
                        "only the failed ones"
                    ]
                )
            # 3. the stage as a whole (minimums, party composition, cross-item links)
            merged = merge_filled(order, prog["filled"])
            notes = list(prog["notes"])
            errors = validate_stage(
                stage, merged, base, ruleset=rules.ruleset, brief=brief, notes=notes
            )
            if not errors:
                row.output = merged.model_dump()
                row.status, row.attempts = "ready", calls
                row.errors = [f"note: {n}" for n in notes]
                row.progress = {}
                await turn.finish(self.session)
                await self.session.flush()
                return True
            # an error that names an item sends that item back with the error; anything else
            # (e.g. a missing minimum) means the outline itself must change on a rerun
            blamed = blame(errors, order, prog["filled"], cfg.primary)
            if not blamed:
                row.progress = {}
                return await fail(errors)
            for r, errs in blamed.items():  # a rerun (or the repair round) refills these
                prog["filled"].pop(r, None)
                prog["item_errors"][r] = errs
            await self._save_progress(row, prog)
        return await fail(errors)

    async def _fill_item(self, h, turn, row, stage, item, items, base, prog, brief, rules, guide):
        cfg = stage.itemized
        primary = cfg.primary
        siblings = {x.ref: KIND[primary] for x in items if x.ref != item.ref}
        errors: list[str] = list(prog["item_errors"].get(item.ref, []))
        used = 0
        for _ in range(ITEM_ATTEMPTS):
            # earlier finished items of this stage are visible as accepted canon
            work = copy.deepcopy(base)
            for x in items:
                if x.ref in prog["filled"]:
                    work.add(stage.key, WorldAuthorOut.model_validate(prog["filled"][x.ref]))
            used += 1
            res = await self._ask(
                h,
                turn,
                stage,
                self._sections(
                    stage,
                    brief,
                    work,
                    row.guidance,
                    errors,
                    rules=rules,
                    head=fill_task(stage, item, items, guide),
                    focus=item_focus(item, items),
                ),
                f"item {item.ref}",
            )
            row.model_run_id = res.model_run_id
            if not res.ok or not isinstance(res.output, WorldAuthorOut):
                errors = [f"output unusable: {res.status} {'; '.join(res.errors)[:300]}"]
                continue
            env: WorldAuthorOut = res.output
            notes: list[str] = []
            if res.status == "salvaged":
                notes.append("the answer was cut off; its complete items were kept")
            entries = getattr(env, primary)
            extra = [x.ref for x in entries if x.ref != item.ref]
            if extra:  # siblings are written in their own steps
                setattr(env, primary, [x for x in entries if x.ref == item.ref])
                notes.append(f"entries for other items dropped: {', '.join(extra)}")
            for sec in sorted(set(stage.sections) - cfg.fill_sections):
                if getattr(env, sec):
                    setattr(env, sec, [])
                    notes.append(f"section {sec} is not part of one item; dropped")
            if not getattr(env, primary):
                errors = [f"the answer must contain the {primary} entry with ref {item.ref}"]
                continue
            errors = validate_stage(
                stage,
                env,
                work,
                ruleset=rules.ruleset,
                brief=brief,
                notes=notes,
                scope="item",
                siblings=siblings,
            )
            if not errors:
                return env, notes, [], used
        return None, [], errors, used

    def _sections(
        self,
        stage: Stage,
        brief: CampaignBrief,
        catalog: Catalog,
        guidance: str | None,
        errors: list[str],
        *,
        rules: RulesEngine | None = None,
        partial: WorldAuthorOut | None = None,
        head: list[str] | None = None,  # itemized outline/fill task instead of the stage task
        focus: set[str] | None = None,  # refs this call is about (an item and its links)
    ) -> dict[str, str]:
        rs = (rules or self.engine).ruleset
        established = [
            f"{f.key}: {f.subject_ref or '-'} {f.predicate} {f.object_ref or ''} {f.value or ''}"
            for f in catalog.established
        ]
        task = head or [
            f"STAGE {stage.key} — {stage.title}.",
            stage.task,
            "Allowed sections (all others must be empty): "
            + "; ".join(FIELD_GUIDE[s] for s in sorted(stage.sections)),
        ]
        task += [
            "Refs are short snake_case ids you invent (loc_*, npc_*, fac_*, ...); reuse earlier "
            "refs exactly as listed. Every ref you use must exist.",
            "Return only NEW content for this stage. Never repeat facts, places, factions or "
            "anything else already listed — it is stored; refer to it by ref instead.",
        ]
        if stage.minimum and head is None:
            task.append("Minimum: " + ", ".join(f"{n} {s}" for s, n in stage.minimum.items()) + ".")
        if rs.modules:
            task.append(
                "Genre modules in play: "
                + ", ".join(m.name for m in rs.modules)
                + ". World constraints: "
                + " ".join(rs.worldgen_constraints())
            )
        if guidance:
            task.append(f"Player guidance for this stage: {guidance}")
        if partial is not None:
            written = [
                x.ref
                for sec in ("locations", "factions", "actors", "items")
                for x in getattr(partial, sec)
            ]
            written += [f.key for f in partial.facts] + [c.ref for c in partial.clues]
            task.append(
                "CONTINUE: your previous answer was cut off. Already written and kept: "
                + ", ".join(written[:40])
                + ". Return ONLY what is still missing so the stage is complete: "
                + " | ".join(errors[:12])
            )
        elif errors:
            task.append(
                "Your previous answer was rejected. Fix exactly these problems: "
                + " | ".join(errors[:12])
            )
        rules = [
            "Attributes: " + ", ".join(k.split(".")[1] for k in rs.attributes),
            "Skills: " + ", ".join(k.split(".")[1] for k in rs.skills),
            "Traits: " + ", ".join(k.split(".")[1] for k in rs.traits),
            "Item templates: " + ", ".join(rs.equipment),
            "Resources: " + ", ".join(k.split(".")[1] for k in rs.resources),
            "Conditions: " + ", ".join(k.split(".")[1] for k in rs.conditions),
            "Difficulties: " + ", ".join(rs.manifest.difficulty_scale),
            "Effect primitives: "
            + ", ".join(sorted(k for k in REGISTRY if k not in ("teleport", "resurrect"))),
        ]
        return {
            "brief": brief.as_context(),
            "established_canon": "\n".join(established) or "none yet",
            "latent_canon": "\n".join(
                catalog.relevant_lines(set(stage.depends_on) | {stage.key}, focus)
            )
            or "nothing yet",
            "task": "\n".join(task),
            "rules_public": "\n".join(rules),
        }

    async def _handle(self, campaign_id: uuid.UUID) -> CampaignHandle:
        c = await self.session.get(Campaign, campaign_id)
        if c is None or c.active_timeline_id is None:
            raise WorldError("campaign not found")
        return CampaignHandle(c.id, c.active_timeline_id)

    # -- preview and start ---------------------------------------------------------------------

    async def preview(self, campaign_id: uuid.UUID, *, include_secrets: bool = False) -> dict:
        run = await self.latest_run(campaign_id)
        if run is None:
            raise WorldError("no generation run")
        stages = await self.stages(run.id)
        out: dict[str, Any] = {"run_id": str(run.id), "status": run.status, "stages": []}
        for st in stages:
            entry: dict[str, Any] = {
                "stage": st.stage_key,
                "status": st.status,
                "errors": st.errors,
            }
            if st.output is not None:
                env = WorldAuthorOut.model_validate(st.output)
                entry["summary"] = env.summary
                entry["counts"] = {
                    s: len(getattr(env, s))
                    for s in (
                        "facts",
                        "locations",
                        "cultures",
                        "factions",
                        "actors",
                        "mysteries",
                        "clues",
                        "items",
                        "opportunities",
                    )
                    if getattr(env, s)
                }
                entry["names"] = [x.name for x in env.locations] + [
                    a.name or a.ref for a in env.actors
                ]
                if include_secrets:
                    entry["secrets"] = [
                        f.predicate for f in env.facts if f.sensitivity == "secret"
                    ] + [m.question for m in env.mysteries]
            out["stages"].append(entry)
        return out

    async def latest_run(self, campaign_id: uuid.UUID) -> GenerationRun | None:
        return (
            (
                await self.session.execute(
                    select(GenerationRun)
                    .where(GenerationRun.campaign_id == campaign_id)
                    .order_by(GenerationRun.created_at.desc())
                )
            )
            .scalars()
            .first()
        )

    async def start(self, campaign_id: uuid.UUID) -> StartResult:
        """Build the world from every accepted stage, check it, and activate the campaign.
        Any failure rolls back the whole build; the campaign stays a generating draft."""
        run = await self.latest_run(campaign_id)
        if run is None:
            raise WorldError("no generation run")
        stages = await self.stages(run.id)
        not_ready = [s.stage_key for s in stages if s.status != "ready"]
        if not_ready:
            raise WorldError(f"stages not ready: {', '.join(not_ready)}")
        envs = [WorldAuthorOut.model_validate(s.output) for s in stages]
        env = combine(envs)
        run_id = run.id
        h = await self._handle(campaign_id)
        await self.session.commit()
        try:
            rules = await self.rules_for(campaign_id)
            async with unit_of_work(self.session):
                builder = WorldBuilder(self.session, h, ruleset=rules.ruleset)
                await builder.build(env, start_hour=env.opening.hour if env.opening else None)
                problems = await quality_errors(self.session, h, builder, env, rules.ruleset)
                if problems:
                    raise WorldError("quality checks failed: " + "; ".join(problems[:10]))
                campaign = await self.session.get(Campaign, campaign_id)
                assert campaign is not None
                brief = CampaignBrief.model_validate(run.brief)
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    await tx.emit(
                        ev.CampaignStarted(
                            generation_run_id=run.id,
                            opening_scene_id=builder.opening_scene,
                            player_actor_id=builder.player,
                        )
                    )
                    campaign.status = "active"
                    campaign.name = brief.title
                    campaign.settings = {
                        **(campaign.settings or {}),
                        "player_canon_policy": "personal",
                        "narration_style": {"tone": ", ".join(brief.genres)},
                        "focus_actor_id": str(builder.player),
                    }
                run.status = "applied"
        except Exception as exc:
            self.session.expire_all()  # the unit of work rolled back: nothing cached is real
            run = await self._run(run_id)
            run.error = f"start failed: {exc}"[:2000]
            await self.session.commit()
            raise
        assert builder.opening_scene and builder.player
        return StartResult(campaign_id, builder.opening_scene, builder.player, builder.party)
