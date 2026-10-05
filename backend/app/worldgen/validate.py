"""Stage validation (orchestration §27: schema/reference validation, established-canon
comparison, rules compatibility, duplicate matching; campaign-generation §15, §25).

`Catalog` is the merged, objective view of every accepted stage so far: refs by kind, facts by
key, actors merged across stages, mysteries. `validate_stage` checks one World Author envelope
against its stage contract and the catalog and returns a list of human-readable errors (empty
= accept). Nothing here writes to the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.engine.effects import REGISTRY
from app.engine.ruleset import Ruleset
from app.worldgen.brief import CampaignBrief
from app.worldgen.envelope import (
    SECTIONS,
    GenActor,
    GenFact,
    GenFaction,
    GenLocation,
    WorldAuthorOut,
)
from app.worldgen.stages import STAGE_BY_KEY, Stage

DETAIL_RANK = {"outline": 0, "latent": 1, "materialized": 2}
ENTITY_KINDS = {"location", "actor", "culture", "conflict", "pressure", "item", "opportunity"}
FORBIDDEN_PRIMITIVES = {"teleport", "resurrect", "modify_attribute"}
ARTIFACT_TIERS = {"low", "minor"}
ATTRS = ("might", "agility", "intellect", "presence", "resolve")
# Core Adventure creation budget (core-adventure-rules §14): attributes begin at 3 with 10 extra
# points, max 8; 8 skill points (+2 ranks from the background's trained skill), max rank 3.
PC_BUDGET = {"attr_min": 3, "attr_max": 8, "attr_total": 25, "skill_max": 3, "skill_total": 10}


def norm_key(prefix: str, raw: str) -> str:
    k = raw.strip().lower().replace(" ", "_")
    return k if k.startswith(prefix + ".") else f"{prefix}.{k}"


def _pred(p: str) -> str:
    return re.sub(r"\s+", " ", p.strip().lower())


def negates(a: str, b: str) -> bool:
    a, b = _pred(a), _pred(b)
    return a == f"not {b}" or b == f"not {a}"


@dataclass
class Catalog:
    """Everything accepted so far, keyed for reference resolution."""

    kinds: dict[str, str] = field(default_factory=dict)  # ref -> kind
    names: dict[str, str] = field(default_factory=dict)  # ref -> display name
    facts: dict[str, GenFact] = field(default_factory=dict)
    fact_stage: dict[str, str] = field(default_factory=dict)
    actors: dict[str, GenActor] = field(default_factory=dict)
    locations: dict[str, Any] = field(default_factory=dict)
    mysteries: dict[str, Any] = field(default_factory=dict)
    factions: dict[str, GenFaction] = field(default_factory=dict)
    mechanics: set[str] = field(default_factory=set)
    established: list[GenFact] = field(default_factory=list)  # incl. pre-existing world canon
    zones: dict[str, set[str]] = field(default_factory=dict)  # location ref -> zone keys
    imported: dict[str, int] = field(default_factory=dict)  # section -> count from an import
    established_actors: set[str] = field(default_factory=set)  # imported people are canon

    @classmethod
    def build(cls, envelopes: list[tuple[str, WorldAuthorOut]]) -> Catalog:
        c = cls()
        for stage_key, env in envelopes:
            c.add(stage_key, env)
        return c

    def add(self, stage_key: str, env: WorldAuthorOut) -> None:
        if stage_key == "import":
            self.established_actors |= {a.ref for a in env.actors}
            for section in SECTIONS:
                val = getattr(env, section)
                if isinstance(val, list) and val:
                    self.imported[section] = self.imported.get(section, 0) + len(val)
        for loc in env.locations:
            merged = merge_location(self.locations.get(loc.ref), loc)
            self.kinds[loc.ref], self.names[loc.ref] = "location", merged.name
            self.locations[loc.ref] = merged
            self.zones[loc.ref] = {z.key for z in merged.zones}
        for c in env.cultures:
            self.kinds[c.ref], self.names[c.ref] = "culture", c.name
        for f in env.factions:
            self.factions[f.ref] = merge_faction(self.factions.get(f.ref), f)
            self.kinds[f.ref], self.names[f.ref] = "faction", self.factions[f.ref].name
        for a in env.actors:
            self.kinds[a.ref] = "actor"
            self.actors[a.ref] = merge_actor(self.actors.get(a.ref), a)[0]
            self.names[a.ref] = self.actors[a.ref].name or a.ref
        for x in env.conflicts:
            self.kinds[x.ref], self.names[x.ref] = "conflict", x.title
        for x in env.pressures:
            self.kinds[x.ref], self.names[x.ref] = "pressure", x.title
        for m in env.mysteries:
            self.kinds[m.ref], self.names[m.ref] = "mystery", m.question
            self.mysteries[m.ref] = m
        for cl in env.clues:
            self.kinds[cl.ref], self.names[cl.ref] = "clue", cl.ref
        for it in env.items:
            self.kinds[it.ref], self.names[it.ref] = "item", it.name
        for o in env.opportunities:
            self.kinds[o.ref], self.names[o.ref] = "opportunity", o.title
        for m in env.mechanics:
            self.mechanics.add(m.key)
        forced = STAGE_BY_KEY[stage_key].forced_canon if stage_key in STAGE_BY_KEY else None
        for f in env.facts:
            if forced:
                f.canon = forced  # type: ignore[assignment]
            self.facts[f.key] = f
            self.fact_stage[f.key] = stage_key
            if f.canon == "established":
                self.established.append(f)

    def truth_keys(self) -> set[str]:
        return {k for m in self.mysteries.values() for k in m.truth_fact_keys}

    def relevant_lines(
        self, stages: set[str], focus: set[str] | None = None, *, max_facts: int = 80
    ) -> list[str]:
        """The canon one generation call needs (09c: late prompts carried the whole catalog,
        13–15k tokens). Every ref stays listed, compactly, so references resolve; facts are
        shown from `stages` (plus the premise and any import) and wherever they mention a
        `focus` ref; the rest are counted, not shown. Validation still checks against the
        whole catalog, so a filtered prompt cannot let a contradiction through."""
        focus = focus or set()
        by_kind: dict[str, list[str]] = {}
        for ref, kind in self.kinds.items():
            name = (self.names.get(ref) or "")[:48]
            by_kind.setdefault(kind, []).append(f"{ref} ({name})" if name and name != ref else ref)
        out = [f"{kind}s: " + "; ".join(refs) for kind, refs in by_kind.items()]
        wanted = stages | {"premise", "import"}
        near, staged, hidden = [], [], 0
        for key, f in self.facts.items():
            mentions = {f.subject_ref, f.object_ref, *f.known_by_refs} & focus
            line = (
                f"fact {key} ({f.canon}, {f.sensitivity}): "
                f"{f.subject_ref or '-'} {f.predicate} {f.object_ref or ''} {f.value or ''}".strip()
            )
            if mentions or key in focus:
                near.append(line)
            elif self.fact_stage.get(key) in wanted:
                staged.append(line)
            else:
                hidden += 1
        shown = (near + staged)[:max_facts]
        hidden += len(near) + len(staged) - len(shown)
        out += shown
        if hidden:
            out.append(
                f"({hidden} further facts from other stages exist and are stored; do not "
                "restate or contradict canon you were not shown; refer to things by ref)"
            )
        return out

    def summary_lines(self, *, include_secrets: bool = True) -> list[str]:
        out = []
        for ref, kind in self.kinds.items():
            out.append(f"{ref} [{kind}] {self.names.get(ref, '')}")
        for key, f in self.facts.items():
            if f.sensitivity == "secret" and not include_secrets:
                continue
            out.append(
                f"fact {key} ({f.canon}, {f.sensitivity}): "
                f"{f.subject_ref or '-'} {f.predicate} {f.object_ref or ''} {f.value or ''}".strip()
            )
        return out


def merge_location(old: GenLocation | None, new: GenLocation) -> GenLocation:
    """Deepen an earlier place (ninth A9 run: the region stage sketched the town, the
    settlement stage materializes it). Detail only ever increases; zones/adjacency/entry come
    from the deeper version; features and simulation state accumulate."""
    if old is None:
        return new
    if DETAIL_RANK[new.detail] < DETAIL_RANK[old.detail]:
        return old
    data = old.model_dump()
    data["detail"] = new.detail
    for k in ("zones", "adjacency", "entry_zone"):
        if getattr(new, k):
            data[k] = new.model_dump()[k]
    data["features"] = list(old.features) + [f for f in new.features if f not in old.features]
    data["simulation_state"] = {**old.simulation_state, **new.simulation_state}
    data["settlement"] = old.settlement or new.settlement
    for k in ("descriptor", "parent_ref", "type"):
        if not data.get(k) or data.get(k) == "site":
            data[k] = getattr(new, k) or data.get(k)
    return GenLocation.model_validate(data)


def merge_faction(old: GenFaction | None, new: GenFaction) -> GenFaction:
    """Refine an earlier power into an actionable faction (seventh A9 run: GLM builds every
    power in the politics stage and adds plans in the factions stage). Non-empty new values
    fill in or extend; the kind becomes the refining stage's."""
    if old is None:
        return new
    data = old.model_dump()
    for k, v in new.model_dump().items():
        if k == "ref":
            continue
        cur = data.get(k)
        if isinstance(v, list):
            data[k] = list(cur or []) + [x for x in v if x not in (cur or [])]
        elif isinstance(v, dict):
            data[k] = {**(cur or {}), **v}
        elif v not in (None, "") and (k == "kind" or not cur):
            data[k] = v
    return GenFaction.model_validate(data)


def merge_actor(old: GenActor | None, new: GenActor) -> tuple[GenActor, list[str]]:
    """Refine an actor: empty fields fill in, lists extend, and a differing value is a
    *revision* — the new value wins and is reported. Whether a revision is allowed is the
    caller's call: latent canon may be revised before play, established canon may not
    (Invariant 9; sixteenth A9 run: the NPC stage rewrote a latent mystery participant)."""
    if old is None:
        return new, []
    conflicts: list[str] = []
    data = old.model_dump()
    for k, v in new.model_dump().items():
        if k == "ref":
            continue
        cur = data.get(k)
        if isinstance(v, list):
            data[k] = list(cur or []) + [x for x in v if x not in (cur or [])]
        elif isinstance(v, dict):
            merged = dict(cur or {})
            for dk, dv in v.items():
                if dk in merged and merged[dk] != dv:
                    conflicts.append(f"actor {new.ref}.{k}.{dk}: {merged[dk]!r} -> {dv!r}")
                merged[dk] = dv
            data[k] = merged
        elif v in (None, "", True, "npc", "standard") and k in (
            "name",
            "descriptor",
            "occupation",
            "location_ref",
            "summary",
            "leads_faction_ref",
            "culture_ref",
            "alive",
            "role",
            "importance",
        ):
            continue  # a default on the refinement never overrides what was set before
        elif cur not in (None, "", []) and cur != v:
            conflicts.append(f"actor {new.ref}.{k}: {cur!r} -> {v!r}")
            data[k] = v
        else:
            data[k] = v
    return GenActor.model_validate(data), conflicts


def validate_stage(
    stage: Stage,
    env: WorldAuthorOut,
    catalog: Catalog,
    *,
    ruleset: Ruleset,
    brief: CampaignBrief,
    final: bool = False,
    notes: list[str] | None = None,
    scope: str = "stage",  # "item": one item of an itemized stage (no whole-stage checks)
    siblings: dict[str, str] | None = None,  # outline refs (ref -> kind) that resolve
) -> list[str]:
    """Returns the errors; deterministic normalizations applied to `env` are appended to
    `notes` (they never widen knowledge or invent references)."""
    errors: list[str] = []
    e = errors.append
    note = (notes if notes is not None else []).append

    # 1b. repeats: content an earlier stage already stored is dropped, and the earlier
    # version stands (third A9 run: GLM re-emitted every earlier fact in the politics stage).
    # Actors are exempt — repeating an actor's ref is how a later stage refines it.
    kind_of_section = {
        "locations": "location",
        "cultures": "culture",
        "factions": "faction",
        "conflicts": "conflict",
        "pressures": "pressure",
        "mysteries": "mystery",
        "clues": "clue",
        "items": "item",
        "opportunities": "opportunity",
    }
    refines_factions = stage.key in ("factions", "local_factions")
    for section, kind in kind_of_section.items():
        kept = []
        for x in getattr(env, section):
            if catalog.kinds.get(x.ref) != kind:
                kept.append(x)
            elif section == "factions" and refines_factions and (x.plan_steps or x.hidden_goal):
                note(f"faction {x.ref!r}: an earlier power refined into an actionable faction")
                kept.append(x)
            elif section == "locations" and _deepen(x, catalog.locations[x.ref], stage):
                note(f"location {x.ref!r}: deepened from {catalog.locations[x.ref].detail}")
                kept.append(x)
            else:
                note(f"{section}: {x.ref!r} repeats earlier content; the earlier version stands")
        setattr(env, section, kept)
    repeated = [f.key for f in env.facts if f.key in catalog.facts]
    if repeated:
        note(f"facts: {len(repeated)} repeated earlier keys dropped ({', '.join(repeated[:5])})")
        env.facts = [f for f in env.facts if f.key not in catalog.facts]
    env.mechanics = [m for m in env.mechanics if m.key not in catalog.mechanics]

    # 1c. the stage decides what kind of power it describes (fourth A9 run: GLM marked
    # politics-stage states as actionable factions, then repeated them in the factions stage)
    forced_kind = {"politics": "polity", "factions": "faction", "local_factions": "faction"}
    if stage.key in forced_kind:
        for f in env.factions:
            if f.kind != forced_kind[stage.key]:
                note(
                    f"faction {f.ref}: kind {f.kind!r} -> {forced_kind[stage.key]!r} ({stage.key})"
                )
                f.kind = forced_kind[stage.key]  # type: ignore[assignment]

    # 1. the stage contract
    for section in SECTIONS:
        val = getattr(env, section)
        if val and section not in stage.sections:
            e(f"section '{section}' is not allowed in stage {stage.key}")
    if stage.key == "opening" and env.opening is None:
        e("the opening stage must set `opening`")
    if stage.forced_canon:
        for f in env.facts:
            f.canon = stage.forced_canon  # type: ignore[assignment]

    # 1d. dotted zone refs (fourteenth A9 run: "loc_store.zone_shop" as a location_ref, and
    # adjacency between zones of different places): split them; cross-place pairs are dropped
    for it in env.items:
        if it.location_ref and "." in it.location_ref:
            loc, _, zone = it.location_ref.partition(".")
            note(f"item {it.ref}: {it.location_ref!r} split into place {loc!r}, zone {zone!r}")
            it.location_ref, it.zone = loc, it.zone or zone
    for loc in env.locations:
        pairs = []
        for pair in loc.adjacency:
            names = [z.split(".", 1)[1] if z.startswith(loc.ref + ".") else z for z in pair]
            if any("." in z for z in names):
                note(f"location {loc.ref}: adjacency {pair} crosses places; dropped")
                continue
            own = {z.key for z in loc.zones}
            if len(names) != 2 or not set(names) <= own:
                note(f"location {loc.ref}: adjacency {pair} names unknown zones; dropped")
                continue
            pairs.append(names)
        loc.adjacency = pairs

    # 4a. ruleset keys: prefixes added; for NPCs and objects an unknown key is dropped or
    # replaced by generic gear and noted (fifteenth A9 run: "document" for item.document).
    # Player characters stay strict.
    def template(key: str, where: str) -> str:
        k = norm_key("item", key)
        if k in ruleset.equipment:
            return k
        note(f"{where}: unknown item template {key!r}; generic gear used")
        return "item.travel_supplies"

    for it in env.items:
        it.template_key = template(it.template_key, f"item {it.ref}")
    for a in env.actors:
        for eq in a.equipment:  # gear is not where a character's power lives: generic is safe
            eq.template_key = template(eq.template_key, f"actor {a.ref} equipment")
        # relationships are -100..100; GLM sometimes writes them 0..10 (twentieth A9 run)
        for rel in a.relationships:
            vals = [
                rel.trust,
                rel.respect,
                rel.affection,
                rel.fear,
                rel.resentment,
                rel.familiarity,
            ]
            if any(vals) and max(abs(v) for v in vals) <= 10:
                for dim in ("trust", "respect", "affection", "fear", "resentment", "familiarity"):
                    setattr(rel, dim, getattr(rel, dim) * 10)
                note(f"actor {a.ref}: relationship with {rel.target_ref} rescaled from 0..10")
        if a.role != "npc":
            continue
        for k in [k for k in a.attributes if not ruleset.has(norm_key("attr", k))]:
            note(f"actor {a.ref}: unknown attribute {k!r} dropped")
            a.attributes.pop(k)
        for k in [k for k in a.skills if not ruleset.has(norm_key("skill", k))]:
            note(f"actor {a.ref}: unknown skill {k!r} dropped")
            a.skills.pop(k)
        unknown_traits = [t for t in a.traits if not ruleset.has(norm_key("trait", t))]
        if unknown_traits:
            note(f"actor {a.ref}: unknown traits {unknown_traits} dropped")
            a.traits = [t for t in a.traits if t not in unknown_traits]

    # 2. refs: new ones unique, existing ones resolvable
    local: dict[str, str] = {}

    def define(ref: str, kind: str, *, refine: bool = False) -> None:
        if ref in local:
            e(f"duplicate ref {ref!r} in this stage")
        elif ref in catalog.kinds and not (refine and catalog.kinds[ref] == kind):
            e(f"ref {ref!r} already exists as a {catalog.kinds[ref]}")
        local[ref] = kind

    for loc in env.locations:
        define(loc.ref, "location", refine=True)  # repeats were filtered above
    for c in env.cultures:
        define(c.ref, "culture")
    for f in env.factions:
        define(f.ref, "faction", refine=stage.key in ("factions", "local_factions"))
    for a in env.actors:
        define(a.ref, "actor", refine=True)
    for x in env.conflicts:
        define(x.ref, "conflict")
    for x in env.pressures:
        define(x.ref, "pressure")
    for m in env.mysteries:
        define(m.ref, "mystery")
    for cl in env.clues:
        define(cl.ref, "clue")
    for it in env.items:
        define(it.ref, "item")
    for o in env.opportunities:
        define(o.ref, "opportunity")
    fact_keys: set[str] = set()
    for f in env.facts:
        if f.key in fact_keys or f.key in catalog.facts:
            e(f"duplicate fact key {f.key!r}")
        fact_keys.add(f.key)
    all_kinds = {**(siblings or {}), **catalog.kinds, **local}
    all_facts = {**catalog.facts, **{f.key: f for f in env.facts}}
    mechanic_keys = catalog.mechanics | {m.key for m in env.mechanics}

    def need(ref: str | None, kinds: set[str] | None, where: str) -> None:
        if ref is None:
            return
        k = all_kinds.get(ref)
        if k is None:
            e(f"{where}: unknown ref {ref!r}")
        elif kinds is not None and k not in kinds:
            e(f"{where}: {ref!r} is a {k}, expected {'/'.join(sorted(kinds))}")

    def ok(ref: str | None, kinds: set[str]) -> bool:
        return ref is not None and all_kinds.get(ref) in kinds

    def soft(refs: list[str], kinds: set[str], where: str) -> list[str]:
        """Soft references (links, not structure) that resolve to nothing are dropped and
        noted: dropping only removes a link or narrows knowledge, never invents."""
        kept = [r for r in refs if ok(r, kinds)]
        if len(kept) != len(refs):
            note(f"{where}: dropped unknown refs {[r for r in refs if r not in kept]}")
        return kept

    def soft_one(ref: str | None, kinds: set[str], where: str) -> str | None:
        if ref is None or ok(ref, kinds):
            return ref
        note(f"{where}: dropped unknown ref {ref!r}")
        return None

    def need_fact(key: str, where: str) -> None:
        if key not in all_facts:
            e(f"{where}: unknown fact key {key!r}")

    anything = ENTITY_KINDS | {"faction"}
    for f in env.facts:
        # A fact's subject/object that names nothing known is folded into its wording: a fact
        # without entity links is still a valid objective proposition (first A9 run: GLM wrote
        # "the region" / "failing" as refs in the premise, where no entities exist yet).
        # Knowers stay strict — knowledge must belong to someone who exists.
        if f.subject_ref and f.subject_ref not in all_kinds:
            note(f"fact {f.key}: subject {f.subject_ref!r} is not a ref; folded into the wording")
            f.predicate = f"{_words(f.subject_ref)} {f.predicate}"
            f.subject_ref = None
        if f.object_ref and f.object_ref not in all_kinds:
            if f.value is None:
                f.value = _words(f.object_ref)
            else:
                f.predicate = f"{f.predicate} {_words(f.object_ref)}"
            f.object_ref = None
        need(f.subject_ref, anything, f"fact {f.key}.subject_ref")
        need(f.object_ref, anything, f"fact {f.key}.object_ref")
        # knowers that do not exist (yet) are dropped: that only ever narrows who knows a
        # fact, never widens it; the NPC stage gives knowledge to real people (second A9 run)
        unknown = [r for r in f.known_by_refs if all_kinds.get(r) != "actor"]
        if unknown:
            note(f"fact {f.key}: dropped knowers that are not actors: {unknown}")
            f.known_by_refs = [r for r in f.known_by_refs if r not in unknown]
    # soft references: links between things (fifth A9 run: routes from a valley GLM never
    # defined). Structural references — where a person lives, where an object is, clue
    # objects, mystery truths, schedules, the opening — stay strict below.
    for loc in env.locations:
        loc.parent_ref = soft_one(loc.parent_ref, {"location"}, f"location {loc.ref}.parent_ref")
    kept_routes = []
    for r in env.routes:
        if ok(r.from_ref, {"location"}) and ok(r.to_ref, {"location"}):
            kept_routes.append(r)
        else:
            note(f"route {r.from_ref}->{r.to_ref}: dropped (unknown place)")
    env.routes = kept_routes
    for c in env.cultures:
        c.homeland_ref = soft_one(c.homeland_ref, {"location"}, f"culture {c.ref}.homeland_ref")
    for f in env.factions:
        f.territory_refs = soft(f.territory_refs, {"location"}, f"faction {f.ref}.territory")
        f.allies = soft(f.allies, {"faction"}, f"faction {f.ref}.allies")
        f.rivals = soft(f.rivals, {"faction"}, f"faction {f.ref}.rivals")
    for a in env.actors:
        need(a.location_ref, {"location"}, f"actor {a.ref}.location_ref")
        a.culture_ref = soft_one(a.culture_ref, {"culture"}, f"actor {a.ref}.culture_ref")
        a.leads_faction_ref = soft_one(
            a.leads_faction_ref, {"faction"}, f"actor {a.ref}.leads_faction_ref"
        )
        a.faction_refs = soft(a.faction_refs, {"faction"}, f"actor {a.ref}.faction_refs")
        for g in a.goals:
            g.target_refs = soft(g.target_refs, anything, f"actor {a.ref}.goal target")
        for b in a.beliefs:
            b.subject_ref = soft_one(b.subject_ref, anything, f"actor {a.ref}.belief subject")
            b.object_ref = soft_one(b.object_ref, anything, f"actor {a.ref}.belief object")
        unknown_k = [k for k in a.knows_fact_keys if k not in all_facts]
        if unknown_k:  # knowledge links narrow, never widen (twenty-second A9 run)
            note(f"actor {a.ref}: knows unknown facts {unknown_k}; dropped")
            a.knows_fact_keys = [k for k in a.knows_fact_keys if k not in unknown_k]
        a.knows_refs = soft(a.knows_refs, ENTITY_KINDS, f"actor {a.ref}.knows_refs")
        rels = [rel for rel in a.relationships if ok(rel.target_ref, {"actor"})]
        if len(rels) != len(a.relationships):
            note(f"actor {a.ref}: dropped relationships with unknown people")
        a.relationships = rels
    for x in env.conflicts:
        x.participant_refs = soft(
            x.participant_refs, {"actor", "faction"}, f"conflict {x.ref}.participants"
        )
    for x in env.pressures:
        x.source_refs = soft(x.source_refs, anything, f"pressure {x.ref}.sources")
    for m in env.mysteries:
        if not m.truth_fact_keys:
            e(f"mystery {m.ref} has no truth facts (truth comes first)")
        for k in m.truth_fact_keys + m.red_herring_fact_keys:
            need_fact(k, f"mystery {m.ref}")
        m.participant_refs = soft(
            m.participant_refs, {"actor", "faction"}, f"mystery {m.ref}.participants"
        )
        for rh in m.red_herring_fact_keys:
            if rh in m.truth_fact_keys:
                e(f"mystery {m.ref}: red herring {rh!r} is also a truth")
            for tk in m.truth_fact_keys:
                a_, b_ = all_facts.get(rh), all_facts.get(tk)
                if a_ and b_ and _same_about(a_, b_) and negates(a_.predicate, b_.predicate):
                    e(f"mystery {m.ref}: red herring {rh!r} contradicts the truth {tk!r}")
    # clues: a clue that cannot be a real route (its mystery is not an earlier stage's — truth
    # precedes clues —, its fact or object does not exist) is dropped and noted; the stage
    # minimum and the whole-world redundancy check still guard solvability
    kept_clues = []
    for cl in env.clues:
        why = None
        if catalog.kinds.get(cl.mystery_ref) != "mystery":
            why = f"mystery {cl.mystery_ref!r} is not from an earlier stage (truth precedes clues)"
        elif cl.supports_fact_key not in all_facts:
            why = f"supported fact {cl.supports_fact_key!r} does not exist"
        elif cl.clue_type in ("physical", "document") and not ok(cl.entity_ref, {"item"}):
            why = f"a {cl.clue_type} clue needs an existing item (entity_ref {cl.entity_ref!r})"
        if why:
            note(f"clue {cl.ref} dropped: {why}")
        else:
            kept_clues.append(cl)
    env.clues = kept_clues
    for it in env.items:
        need(it.location_ref, {"location"}, f"item {it.ref}.location_ref")
        need(it.holder_ref, {"actor"}, f"item {it.ref}.holder_ref")
        if not it.location_ref and not it.holder_ref:
            e(f"item {it.ref} is nowhere (needs location_ref or holder_ref)")
        if it.location_ref and it.zone:
            here = next((x for x in env.locations if x.ref == it.location_ref), None) or (
                catalog.locations.get(it.location_ref)
            )
            zones = [z.key for z in here.zones] if here is not None else []
            if it.zone not in zones:
                if zones:
                    moved = (here.entry_zone if here.entry_zone in zones else None) or zones[0]
                    note(
                        f"item {it.ref}: zone {it.zone!r} unknown at {it.location_ref}; "
                        f"placed in {moved!r}"
                    )
                    it.zone = moved
                else:
                    # the corrective retry needs somewhere legal to put it (A9, 09c run)
                    zoned = [
                        r
                        for r, x in {
                            **catalog.locations,
                            **{x.ref: x for x in env.locations},
                        }.items()
                        if x.zones
                    ]
                    e(
                        f"item {it.ref}: {it.location_ref} has no zones to place it in; put it "
                        f"in a place that has zones ({', '.join(zoned[:6]) or 'none yet'}) or "
                        "give it to a person (holder_ref)"
                    )
        if it.concealed and not it.location_ref:
            e(f"item {it.ref}: only an item lying somewhere can be concealed")
        if it.concealment_difficulty and it.concealment_difficulty not in (
            ruleset.manifest.difficulty_scale
        ):
            e(f"item {it.ref}: unknown difficulty {it.concealment_difficulty!r}")
        if it.template_key not in ruleset.equipment:
            e(f"item {it.ref}: unknown item template {it.template_key!r}")
        if it.document is not None:
            it.document.author_ref = soft_one(
                it.document.author_ref, {"actor"}, f"item {it.ref}.document.author"
            )
            it.document.names_refs = soft(
                it.document.names_refs, ENTITY_KINDS, f"item {it.ref}.document.names"
            )
            missing = [k for k in it.document.conveys_fact_keys if k not in all_facts]
            if missing:
                note(f"item {it.ref}: the document's unknown facts {missing} dropped")
                it.document.conveys_fact_keys = [
                    k for k in it.document.conveys_fact_keys if k not in missing
                ]
        if it.mechanics_key and it.mechanics_key not in mechanic_keys:
            e(f"item {it.ref}: unknown mechanics_key {it.mechanics_key!r}")
    thin = [o.ref for o in env.opportunities if len(o.routes) < 2]
    if thin:
        note(f"opportunities {thin} dropped: fewer than two discovery routes")
        env.opportunities = [o for o in env.opportunities if o.ref not in thin]
    for o in env.opportunities:
        o.pressure_ref = soft_one(o.pressure_ref, {"pressure"}, f"opportunity {o.ref}.pressure")
        for r in o.routes:
            r.via_ref = soft_one(r.via_ref, anything, f"opportunity {o.ref}.route")

    # schedules are optional world motion: one that cannot resolve is dropped and noted; a
    # fact.establish whose fact is only written inside its patch becomes that latent fact
    # (eighteenth A9 run)
    kept_schedules = []
    for s in env.schedules:
        ok_ = True
        if s.type == "fact.establish":
            if s.fact_key and s.fact_key not in all_facts and s.patch.get("predicate"):
                gf = GenFact(
                    key=s.fact_key,
                    predicate=str(s.patch["predicate"]),
                    sensitivity=s.patch.get("sensitivity", "public")
                    if s.patch.get("sensitivity") in ("public", "private", "secret")
                    else "public",
                    canon="latent",
                )
                env.facts.append(gf)
                all_facts[gf.key] = gf
                note(f"schedule {s.key}: fact {s.fact_key!r} taken from its patch")
            ok_ = bool(s.fact_key) and s.fact_key in all_facts
        elif s.type == "clue.destroy":
            ok_ = ok(s.clue_ref, {"clue"})
        elif s.type == "location.state":
            ok_ = ok(s.location_ref, {"location"})
        elif s.type == "actor.travel":
            ok_ = ok(s.actor_ref, {"actor"}) and ok(s.location_ref, {"location"})
        elif s.type == "decision":
            ok_ = ok(s.faction_ref or s.actor_ref, {"faction", "actor"})
        if ok_:
            kept_schedules.append(s)
        else:
            note(f"schedule {s.key} ({s.type}): references do not resolve; dropped")
    env.schedules = kept_schedules
    if env.opening is not None:
        op = env.opening
        need(op.location_ref, {"location"}, "opening.location_ref")
        loc = catalog.locations.get(op.location_ref) or next(
            (x for x in env.locations if x.ref == op.location_ref), None
        )
        if loc is not None and loc.detail != "materialized":
            e("opening.location_ref must be a materialized location")
        for r in op.present_refs:
            need(r, {"actor"}, "opening.present_refs")
        # people present must be there: party members are brought to the opening place (the
        # builder moves them); an NPC who lives elsewhere is left out of the scene
        present = []
        for r in op.present_refs:
            a = catalog.actors.get(r)
            if a is not None and a.role == "npc" and a.location_ref != op.location_ref:
                note(f"opening: {r} lives at {a.location_ref}, not here; left out of the scene")
                continue
            present.append(r)
        op.present_refs = present
        zones = catalog.zones.get(op.location_ref, set())
        for r, z in list(op.positions.items()):
            if r not in op.present_refs or (zones and z not in zones):
                note(f"opening.positions: {r}->{z} dropped (not present or not a zone)")
                op.positions.pop(r)
        humans = [r for r, a in catalog.actors.items() if a.role == "pc_human"]
        for h in humans:
            if h not in op.present_refs:
                e(f"opening: the player character {h!r} must be present")

    if stage.key == "party" and catalog.imported.get("actors"):
        stage = Stage(stage.key, stage.title, stage.task, stage.sections, stage.depends_on, {})
    for section, n in ({} if scope == "item" else stage.minimum).items():
        # content the user imported counts toward a stage's minimum (the stage extends it)
        have = len(getattr(env, section) or []) + catalog.imported.get(section, 0)
        if have < n:
            e(f"stage {stage.key} needs at least {n} {section}")

    # 3. depth policy
    for loc in env.locations:
        # distant content stays shallow by clamping, not by rejecting the stage (sixth A9 run:
        # a geography region came back latent with detail the stage may not produce)
        if DETAIL_RANK[loc.detail] > DETAIL_RANK[stage.max_detail]:
            note(f"location {loc.ref}: {loc.detail} clamped to {stage.max_detail} ({stage.key})")
            loc.detail = stage.max_detail  # type: ignore[assignment]
        if loc.zones and loc.detail != "materialized":
            note(f"location {loc.ref}: zones dropped (only materialized places have zones)")
            loc.zones, loc.adjacency, loc.entry_zone = [], [], None
        if loc.detail == "materialized" and not loc.zones:
            e(f"location {loc.ref}: a materialized location needs zones")
        keys = {z.key for z in loc.zones}
        for pair in loc.adjacency:
            if len(pair) != 2 or not set(pair) <= keys:
                e(f"location {loc.ref}: adjacency {pair} names unknown zones")
        if loc.entry_zone and loc.entry_zone not in keys:
            e(f"location {loc.ref}: entry_zone {loc.entry_zone!r} is not a zone")

    # 4. rules compatibility
    for a in env.actors:
        # behaviour dimensions are 0..1; GLM sometimes writes them on a 1..10 scale
        for k, v in list(a.dimensions.items()):
            if v > 1:
                a.dimensions[k] = round(min(1.0, v / 10), 2)
                note(f"actor {a.ref}: dimension {k} {v} rescaled to {a.dimensions[k]}")
            elif v < 0:
                a.dimensions[k] = 0.0
    for a in env.actors:
        # NPC numbers outside the ruleset's scale are clamped and noted (eighth A9 run: a
        # scholar with Lore 7); player characters stay strict under the creation budget
        for k, v in list(a.attributes.items()):
            key = norm_key("attr", k)
            if not ruleset.has(key):
                e(f"actor {a.ref}: unknown attribute {k!r}")
            elif not 1 <= int(v) <= 10:
                if a.role == "npc":
                    a.attributes[k] = max(1, min(10, int(v)))
                    note(f"actor {a.ref}: {k} {v} clamped to {a.attributes[k]}")
                else:
                    e(f"actor {a.ref}: {k} {v} outside 1..10")
        for k, v in list(a.skills.items()):
            if not ruleset.has(norm_key("skill", k)):
                e(f"actor {a.ref}: unknown skill {k!r}")
            elif not 0 <= int(v) <= 5:
                if a.role == "npc":
                    a.skills[k] = max(0, min(5, int(v)))
                    note(f"actor {a.ref}: skill {k} {v} clamped to {a.skills[k]}")
                # player characters: fit_pc_budget below clamps and records it
        for t in a.traits:
            if not ruleset.has(norm_key("trait", t)):
                e(f"actor {a.ref}: unknown trait {t!r}")
        for eq in a.equipment:
            eq.template_key = norm_key("item", eq.template_key)
            if eq.template_key not in ruleset.equipment:
                e(f"actor {a.ref}: unknown item template {eq.template_key!r}")
        if a.role != "npc" and stage.key not in ("party", "import"):
            e(f"actor {a.ref}: player characters belong to the party stage")
        if a.role != "npc":
            for change in fit_pc_budget(a, ruleset):
                note(f"party member {a.ref}: {change}")
            errors.extend(pc_budget_errors(a))
    for m in env.mechanics:
        errors.extend(mechanic_errors(m.model_dump(), ruleset))

    # 5. established canon cannot be contradicted
    truths = {k: all_facts[k] for k in catalog.truth_keys() if k in all_facts}
    for f in env.facts:
        for old in catalog.established:
            if _same_about(f, old) and (
                negates(f.predicate, old.predicate)
                or (_pred(f.predicate) == _pred(old.predicate) and f.value != old.value)
            ):
                e(f"fact {f.key} contradicts established canon {old.key!r}")
        for tk, t in truths.items():
            if _same_about(f, t) and negates(f.predicate, t.predicate):
                e(f"fact {f.key} contradicts the locked truth {tk!r}")
    for a in env.actors:
        _merged, revisions = merge_actor(catalog.actors.get(a.ref), a)
        for c in revisions:
            if a.ref in catalog.established_actors:
                e(f"refinement contradicts established canon: {c}")
            else:
                note(f"latent actor revised: {c}")

    # 6. stage-specific substance
    if stage.key in ("factions", "local_factions"):
        for f in env.factions:
            if f.kind == "faction" and not f.plan_steps:
                e(f"faction {f.ref} needs at least one plan step to be actionable")
    if stage.key == "npcs":
        for a in env.actors:
            if a.importance in ("full", "important") and not (
                a.goals or (catalog.actors.get(a.ref) and catalog.actors[a.ref].goals)
            ):
                note(f"NPC {a.ref} has no goals; treated as a standard NPC")
                a.importance = "standard"  # type: ignore[assignment]
            prior = catalog.actors.get(a.ref)
            if not (a.location_ref or (prior and prior.location_ref)):
                e(f"NPC {a.ref} needs a home location")
    if stage.key == "party":
        # the party = imported character sheets (refined here) + what this stage adds; one
        # item (scope "item") gets the per-member rules, the whole stage also its composition
        view = {r: a for r, a in catalog.actors.items() if a.role != "npc"}
        for a in env.actors:
            view[a.ref] = merge_actor(catalog.actors.get(a.ref), a)[0]
        humans = [a for a in view.values() if a.role == "pc_human"]
        ais = [a for a in view.values() if a.role == "pc_ai"]
        if scope == "stage" and len(humans) != 1:
            e("the party stage must define exactly one player character (role pc_human)")
        if scope == "stage" and len(ais) != brief.party_ai_companions:
            e(f"the brief asks for {brief.party_ai_companions} AI companion(s); got {len(ais)}")
        party_refs = {a.ref for a in humans + ais} | set(siblings or {})
        members = (
            humans + ais
            if scope == "stage"
            else [view[a.ref] for a in env.actors if view[a.ref].role != "npc"]
        )
        for a in members:
            if not a.location_ref:
                e(f"party member {a.ref} needs a location")
            if a.role == "pc_ai" and not a.goals:
                e(f"AI companion {a.ref} needs goals")
            if a.role == "pc_ai" and not any(r.target_ref in party_refs for r in a.relationships):
                e(f"AI companion {a.ref} needs a reason to travel with the party (relationships)")
        for a in env.actors:
            for k in a.knows_fact_keys:
                f = all_facts.get(k)
                secret = k in catalog.truth_keys() or (f is not None and f.sensitivity == "secret")
                if a.role != "npc" and secret:
                    e(f"party member {a.ref} may not start knowing secret {k!r}")
    if final:
        errors.extend(final_errors(catalog))
    return errors


def _deepen(new: GenLocation, old: GenLocation, stage: Stage) -> bool:
    """May this stage's repeat of an earlier place deepen it? Only toward the stage's maximum.
    A repeat at the same depth in a stage allowed to go deeper is promoted one level when the
    next level needs nothing more (eleventh A9 run: the region stage re-listed geography's
    outline regions); materialized always needs zones."""
    old_rank, max_rank = DETAIL_RANK[old.detail], DETAIL_RANK[stage.max_detail]
    if old_rank >= max_rank:
        return False
    if DETAIL_RANK[new.detail] <= old_rank:
        promoted = {0: "latent", 1: "materialized"}[old_rank]
        if promoted == "materialized" and not new.zones:
            return False
        new.detail = promoted  # type: ignore[assignment]
    if DETAIL_RANK[new.detail] > max_rank:
        return False
    return new.detail != "materialized" or bool(new.zones)


def _words(ref: str) -> str:
    return ref.replace("_", " ").strip()


def _same_about(a: GenFact, b: GenFact) -> bool:
    return a.subject_ref == b.subject_ref and a.object_ref == b.object_ref


def fit_pc_budget(a: GenActor, ruleset: Ruleset) -> list[str]:
    """Fit a player character's sheet to the Core Adventure creation budget, deterministically
    (the engine owns mechanics; the model proposes): missing attributes start at the base,
    each attribute is clamped to 3..8, the highest come down until the total fits, skills are
    capped at 3 and the lowest trimmed until the total fits, unknown traits are dropped and at
    most two kept. Returns what changed."""
    changes: list[str] = []
    attrs = {norm_key("attr", k).split(".", 1)[1]: int(v) for k, v in a.attributes.items()}
    attrs = {k: v for k, v in attrs.items() if k in ATTRS}
    for k in ATTRS:
        if k not in attrs:
            attrs[k] = PC_BUDGET["attr_min"]
            changes.append(f"{k} missing; set to {PC_BUDGET['attr_min']}")
    for k, v in list(attrs.items()):
        c = max(PC_BUDGET["attr_min"], min(PC_BUDGET["attr_max"], v))
        if c != v:
            changes.append(f"{k} {v} -> {c}")
            attrs[k] = c
    while sum(attrs.values()) > PC_BUDGET["attr_total"]:
        k = max(attrs, key=lambda x: (attrs[x], x))
        attrs[k] -= 1
        changes.append(f"{k} lowered to fit the attribute total")
    skills: dict[str, int] = {}
    for k, v in a.skills.items():
        key = norm_key("skill", k).split(".", 1)[1]
        if not ruleset.has(f"skill.{key}"):
            changes.append(f"unknown skill {k!r} dropped")
            continue
        skills[key] = max(0, min(PC_BUDGET["skill_max"], int(v)))
        if skills[key] != int(v):
            changes.append(f"skill {key} {v} -> {skills[key]}")
        if skills[key] == 0:  # an untrained skill is no entry (09c A9 run: rank 0 went to -9)
            skills.pop(key)
    while sum(skills.values()) > PC_BUDGET["skill_total"]:
        k = min(skills, key=lambda x: (skills[x], x))
        skills[k] -= 1
        if skills[k] <= 0:
            skills.pop(k)
        changes.append(f"skill {k} trimmed to fit the skill total")
    traits = [t for t in a.traits if ruleset.has(norm_key("trait", t))]
    if len(traits) != len(a.traits):
        changes.append("unknown traits dropped")
    if len(traits) > 2:
        changes.append(f"traits {traits[2:]} dropped (two allowed)")
        traits = traits[:2]
    a.attributes, a.skills, a.traits = attrs, skills, traits
    return sorted(set(changes), key=changes.index)


def pc_budget_errors(a: GenActor) -> list[str]:
    out = []
    attrs = {norm_key("attr", k): int(v) for k, v in a.attributes.items()}
    missing = [x for x in ATTRS if f"attr.{x}" not in attrs]
    if missing:
        out.append(f"{a.ref}: player character needs all five attributes (missing {missing})")
    for k, v in attrs.items():
        if not PC_BUDGET["attr_min"] <= v <= PC_BUDGET["attr_max"]:
            out.append(f"{a.ref}: starting {k} {v} outside {PC_BUDGET['attr_min']}..8")
    if sum(attrs.values()) > PC_BUDGET["attr_total"]:
        out.append(f"{a.ref}: attributes total {sum(attrs.values())} > {PC_BUDGET['attr_total']}")
    for k, v in a.skills.items():
        if int(v) > PC_BUDGET["skill_max"]:
            out.append(f"{a.ref}: starting skill {k} rank {v} > 3")
    if sum(int(v) for v in a.skills.values()) > PC_BUDGET["skill_total"]:
        out.append(f"{a.ref}: skill ranks total > {PC_BUDGET['skill_total']}")
    if len(a.traits) > 2:
        out.append(f"{a.ref}: at most two starting traits")
    return out


# Item effects (frostbridge §23, rules-engine §35): the primitives an item may carry and the
# parameters each one actually reads. A registered primitive is not enough — `create_entity`
# or `reveal_information` with invented parameters validates structurally and means nothing
# in play (first A9 run, 2026-10-04).
ITEM_PRIMITIVES: dict[str, dict[str, str]] = {
    "modify_check": {"check": "check", "op": "op", "amount": "small_int"},
    "modify_resource": {"resource": "resource", "amount": "amount"},
    "restore_resource": {"resource": "resource", "amount": "amount"},
    "deal_damage": {"amount": "amount", "damage_type": "damage_type"},
    "apply_condition": {"condition": "condition", "intensity": "small_int"},
    "remove_condition": {"condition": "condition"},
    "grant_capability": {"capability": "capability"},
}
REQUIRED = {
    "modify_resource": {"resource", "amount"},
    "restore_resource": {"resource", "amount"},
    "deal_damage": {"amount"},
    "apply_condition": {"condition"},
    "remove_condition": {"condition"},
    "grant_capability": {"capability"},
}
COMMON_PARAMS = {"duration_seconds", "uses_per_day", "when", "note"}
LOW_DICE = re.compile(r"^(1d4|1d6|1d8|2d4)([+-][0-3])?$")
CAPABILITY = re.compile(r"^[a-z][a-z_]*(:[a-z_]+)?$")


def _param_error(key: str, kind: str, v: Any, ruleset: Ruleset | None) -> str | None:
    if kind == "small_int":
        return None if isinstance(v, int) and -3 <= v <= 3 else f"{key} must be an integer -3..3"
    if kind == "amount":
        if isinstance(v, int):
            return None if -6 <= v <= 6 else f"{key} {v} is beyond a low-tier item"
        return (
            None
            if isinstance(v, str) and LOW_DICE.match(v)
            else f"{key} {v!r} is not low-tier dice"
        )
    if kind == "op":
        return None if v in ("add", "subtract", "advantage", "disadvantage") else f"bad op {v!r}"
    if kind == "check":
        ok = v == "check.*" or (ruleset is not None and v in ruleset.checks)
        return None if ok else f"unknown check {v!r}"
    if kind in ("resource", "condition", "damage_type"):
        return (
            None
            if ruleset is None or (isinstance(v, str) and ruleset.has(v))
            else f"unknown {kind} {v!r}"
        )
    if kind == "capability":
        return None if isinstance(v, str) and CAPABILITY.match(v) else f"bad capability {v!r}"
    return None


def mechanic_errors(definition: dict[str, Any], ruleset: Ruleset | None = None) -> list[str]:
    """Generated mechanics are structurally valid compositions of item-safe primitives
    (Invariant 12): ≤ 1 passive + ≤ 1 activated, low tier, the parameters each primitive
    reads and nothing else, no template placeholders."""
    out = []
    key = definition.get("key", "?")
    effects = [x for x in (definition.get("passive"), definition.get("activated")) if x]
    if not effects:
        out.append(f"mechanic {key}: needs a passive or an activated effect")
    for eff in effects:
        t = eff.get("type")
        if t in FORBIDDEN_PRIMITIVES or t not in REGISTRY:
            out.append(f"mechanic {key}: effect {t!r} is forbidden or unregistered")
            continue
        if t not in ITEM_PRIMITIVES:
            out.append(
                f"mechanic {key}: {t!r} is not an item effect; use one of "
                + ", ".join(sorted(ITEM_PRIMITIVES))
            )
            continue
        params = dict(eff.get("params") or {})
        if params.get("permanent"):
            out.append(f"mechanic {key}: permanent effects are forbidden")
        allowed = ITEM_PRIMITIVES[t]
        for pk in REQUIRED.get(t, set()):
            if pk not in params:
                out.append(f"mechanic {key}: {t} needs {pk!r}")
        for pk, v in params.items():
            if pk in COMMON_PARAMS:
                if pk in ("duration_seconds", "uses_per_day") and not (
                    isinstance(v, int) and 0 < v <= 86400
                ):
                    out.append(f"mechanic {key}: {pk} must be a positive integer")
                continue
            if pk not in allowed:
                out.append(f"mechanic {key}: {t} does not read {pk!r}")
                continue
            err = _param_error(pk, allowed[pk], v, ruleset)
            if err:
                out.append(f"mechanic {key}: {t}: {err}")
        if any("{" in str(v) for v in params.values()):
            out.append(f"mechanic {key}: template placeholders are not mechanics")
    if definition.get("tier") not in ARTIFACT_TIERS:
        out.append(f"mechanic {key}: tier must be low or minor")
    if "{" in str(definition.get("description", "")):
        out.append(f"mechanic {key}: the description contains a template placeholder")
    return out


def final_errors(catalog: Catalog) -> list[str]:
    """Whole-world checks once every stage is in (campaign-generation §25, the parts that are
    visible before building)."""
    out = []
    if not catalog.mysteries:
        out.append("the world needs at least one fixed-truth mystery")
    humans = [a for a in catalog.actors.values() if a.role == "pc_human"]
    if len(humans) != 1:
        out.append("exactly one player character is required")
    settlements = [x for x in catalog.locations.values() if x.settlement]
    if not settlements:
        out.append("no starting settlement (a location with settlement: true)")
    return out
