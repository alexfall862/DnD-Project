"""ConsequenceService: validate and apply consequences from the closed vocabulary
(`app/domain/consequences.py`, DECISIONS 10d).

Proposals come from the Rules Adjudicator (per check branch), from NPC actors and AI players
(only what they can do themselves), or from the engine's own safety net. Each one is checked
before anything changes:

- every reference resolves to the proposer's candidates (people, places, zones, items) or to
  a situation it can see;
- amounts are bounded;
- at most `MAX_PER_BRANCH` per proposal;
- an actor's own proposals must be about itself (`self_param`), or about an obstacle it holds.

Each applied consequence commits a `consequence.applied` event, and the domain events it
implies (situations, relationships, identity, items, travel, effects) in the same unit of
work. A rejected one changes nothing and is reported to dev notes with the reason.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.domain.consequences import MAX_PER_BRANCH, SPECS
from app.engine.core import RulesEngine
from app.persistence.models import Actor, Entity, Event, PartyMembership, Scene, Situation
from app.services.actions import ActionService
from app.services.candidates import Candidate
from app.services.events import EventTransaction
from app.services.situations import (
    DEFAULT_OBSTACLE_SECONDS,
    DEFAULT_WAYS_PAST,
    MAX_OBSTACLE_SECONDS,
    SituationService,
)
from app.services.world import CampaignHandle, WorldError, WorldService

ATTITUDE_STEP = 10  # one step of change_attitude in relationship points
DIMENSIONS = ("trust", "respect", "affection", "fear")
DICE_RE = re.compile(r"^\s*(\d{0,2})d(\d{1,2})\s*([+-]\s*\d{1,2})?\s*$", re.I)


class ConsequenceError(ValueError):
    pass


@dataclass
class ConsequenceContext:
    h: CampaignHandle
    scene: Scene
    actor_id: uuid.UUID  # who earned it (the one acting)
    proposer_id: uuid.UUID | None  # the actor proposing it (an NPC's own proposal); None = ruling
    cands: list[Candidate]  # refs as the proposer (or, for a ruling, the acting player) sees them
    source: str  # ruling | actor | engine
    branch: str | None = None
    turn_id: uuid.UUID | None = None
    names: dict[uuid.UUID, str] = field(default_factory=dict)  # actor id -> known as (player)
    # whom an actor's say-so is for (the player who addressed it); a ruling's is the actor
    focus_actor_id: uuid.UUID | None = None


@dataclass
class Applied:
    kind: str
    ok: bool
    text: str = ""  # what happened, in the player's terms
    reason: str = ""  # why it was rejected
    params: dict[str, Any] = field(default_factory=dict)
    touched: set[str] = field(default_factory=set)  # situation ids resolved / actor ids moved
    people: set[uuid.UUID] = field(default_factory=set)  # everyone it names (resolved)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ok": self.ok, "text": self.text, "reason": self.reason}


ESCORT_RE = re.compile(
    r"\b(accompan\w*|escort\w*|travel\w* with|come with|go with|goes with|protect\w*|guard\w*|"
    r"follow\w*|lead\w* (?:us|them|the party)|take (?:us|them|the party))\b",
    re.I,
)
IDENTITY_PARAMS = (
    "obstacle",
    "label",
    "to",
    "person",
    "who",
    "status",
    "name",
    "item",
    "seller",
    "from",
    "debtor",
    "description",
    "text",
    "clue",
    "zone",
)


def identity(raw: Any) -> str:
    """What makes two proposals the same consequence: the kind and what it is about (not
    its amounts or durations)."""
    if not isinstance(raw, dict):
        return repr(raw)
    kind = str(raw.get("kind") or raw.get("type") or "").lower()
    params = {**raw, **(raw.get("params") if isinstance(raw.get("params"), dict) else {})}
    about = [f"{k}={str(params[k]).strip().lower()}" for k in IDENTITY_PARAMS if params.get(k)]
    return kind + "|" + "|".join(about)


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2}


class ConsequenceService:
    def __init__(
        self,
        session: AsyncSession,
        engine: RulesEngine,
        *,
        actions: ActionService | None = None,
        scenes: Any = None,
    ) -> None:
        self.session = session
        self.engine = engine
        self.actions = actions or ActionService(session, engine)
        if scenes is None:
            from app.services.scenes import SceneService

            scenes = SceneService(session)
        self.scenes = scenes
        self.situations = SituationService(session)
        self.world = WorldService(session)

    # -- entry ---------------------------------------------------------------------------------

    async def apply_all(self, c: ConsequenceContext, items: list[Any] | None) -> list[Applied]:
        out: list[Applied] = []
        unique: list[Any] = []
        seen: set[str] = set()
        for raw in items or []:
            key = identity(raw)
            if key not in seen:  # the same consequence twice is one consequence (A9 eval)
                seen.add(key)
                unique.append(raw)
        for raw in unique[:MAX_PER_BRANCH]:
            if not isinstance(raw, dict):
                out.append(Applied(str(raw)[:30], False, reason="not an object"))
                continue
            kind = str(raw.get("kind") or raw.get("type") or "").strip().lower()
            params = {k: v for k, v in raw.items() if k not in ("kind", "type")}
            if isinstance(raw.get("params"), dict):  # the effect-step shape, tolerated
                params = {**params.pop("params", {}), **raw["params"]}
            out.append(await self.apply_one(c, kind, params))
        return out

    async def apply_one(self, c: ConsequenceContext, kind: str, params: dict[str, Any]) -> Applied:
        spec = SPECS.get(kind)
        if spec is None:
            return Applied(kind, False, reason="not a known consequence")
        missing = [p for p in spec.required if params.get(p) in (None, "", [])]
        if missing:
            return Applied(kind, False, reason=f"missing {', '.join(missing)}", params=params)
        if c.source == "actor" and not spec.actor_may:
            return Applied(
                kind, False, reason="an actor cannot cause that by itself", params=params
            )
        fn = getattr(self, f"_k_{kind}")
        self._people: set[uuid.UUID] = set()
        try:
            if c.source == "actor" and spec.self_param:
                who = await self._person(c, params.get(spec.self_param), allow_party=False)
                if who != [c.proposer_id]:
                    raise ConsequenceError(f"{spec.self_param} must be the actor itself")
            res: Applied = await fn(c, params)
        except (ConsequenceError, WorldError) as exc:
            return Applied(kind, False, reason=str(exc), params=params)
        res.params = params
        res.people = set(self._people)
        return res

    async def _record(
        self, c: ConsequenceContext, kind: str, params: dict[str, Any], result: str
    ) -> tuple[EventTransaction, Event]:
        """Open the unit of work for one consequence: its `consequence.applied` event."""
        tx = EventTransaction(self.session, c.h.campaign_id, c.h.timeline_id)
        await tx.__aenter__()
        tx.created_by_type = {"ruling": "ai", "actor": "ai"}.get(c.source, "engine")
        tx.created_by_id = c.proposer_id or c.actor_id
        event = await tx.emit(
            ev.ConsequenceApplied(
                kind=kind,
                params={k: v for k, v in params.items() if isinstance(v, (str, int, float, list))},
                actor_id=c.actor_id,
                source=c.source,
                branch=c.branch,
                result=result[:300],
            ),
            scene=c.scene,
            location_id=c.scene.location_id,
        )
        return tx, event

    async def _done(self, tx: EventTransaction) -> None:
        await tx.__aexit__(None, None, None)

    # -- references ----------------------------------------------------------------------------

    @staticmethod
    def _for(c: ConsequenceContext) -> uuid.UUID:
        """The one the consequence is for: the player an actor answered, or the one acting."""
        return c.focus_actor_id or c.actor_id

    def _cand(self, c: ConsequenceContext, ref: Any, kinds: tuple[str, ...]) -> Candidate | None:
        if not isinstance(ref, str) or not ref.strip():
            return None
        r = ref.strip()
        pool = [x for x in c.cands if x.kind in kinds]
        for x in pool:
            if r in (x.ref, x.id) or r.lower() == x.known_as.lower():
                return x
        slugged = re.sub(r"[^a-z0-9]+", "_", r.lower()).strip("_")
        for x in pool:
            if slugged == x.ref:
                return x
        words = _tokens(r.replace("_", " "))
        scored = sorted(
            ((len(_tokens(x.known_as) & words), x) for x in pool if x.known_as != "you"),
            key=lambda t: -t[0],
        )
        if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            return scored[0][1]
        return None

    async def _party(self, actor_id: uuid.UUID) -> list[uuid.UUID]:
        parties = select(PartyMembership.party_id).where(PartyMembership.actor_id == actor_id)
        ids = set(
            (
                await self.session.execute(
                    select(PartyMembership.actor_id).where(PartyMembership.party_id.in_(parties))
                )
            )
            .scalars()
            .all()
        ) | {actor_id}
        here = []
        for a in ids:
            actor = await self.session.get(Actor, a)
            if actor is not None and actor.current_scene_id == (
                (await self.session.get(Actor, actor_id)).current_scene_id  # type: ignore[union-attr]
            ):
                here.append(a)
        return sorted(here, key=lambda x: (x != actor_id, str(x)))

    async def _person(
        self, c: ConsequenceContext, ref: Any, *, allow_party: bool = True
    ) -> list[uuid.UUID]:
        r = str(ref or "").strip().lower()
        if r in ("self", "me", "myself") and c.proposer_id is not None:
            return [c.proposer_id]
        if r in ("you", "player", "them", "") or r == str(self._for(c)):
            return [self._for(c)]
        if r in ("self", "actor", "me", "myself") or r == str(c.actor_id):
            return [c.actor_id]
        if r in ("party", "the party", "everyone", "us", "all"):
            if not allow_party:
                raise ConsequenceError("expected one person, not the party")
            return await self._party(self._for(c))
        cand = self._cand(c, ref, ("actor",))
        if cand is None or not cand.id:
            raise ConsequenceError(f"unknown person {ref!r}")
        getattr(self, "_people", set()).add(uuid.UUID(cand.id))
        return [uuid.UUID(cand.id)]

    async def _one(self, c: ConsequenceContext, ref: Any) -> uuid.UUID:
        return (await self._person(c, ref, allow_party=False))[0]

    def _place(self, c: ConsequenceContext, ref: Any) -> Candidate:
        cand = self._cand(c, ref, ("location",))
        if cand is None:
            raise ConsequenceError(f"unknown place {ref!r}")
        return cand

    async def _visible(self, c: ConsequenceContext) -> list[Situation]:
        viewer = c.proposer_id or c.actor_id
        sits = await self.situations.visible_to(viewer)
        if c.source == "ruling":  # an objective role: everything held here
            now = await self.situations.now(c.h.timeline_id)
            seen = {s.id for s in sits}
            sits += [
                s
                for s in await self.situations.at_location(
                    c.h.campaign_id, c.scene.location_id, now
                )
                if s.id not in seen
            ]
        return sits

    async def _obstacle(self, c: ConsequenceContext, ref: Any) -> Situation:
        s = await self.situations.resolve_ref(
            [x for x in await self._visible(c) if x.kind == "obstacle"], ref
        )
        if s is None:
            raise ConsequenceError(f"unknown obstacle {ref!r}")
        if c.source == "actor" and s.holder_actor_id != c.proposer_id:
            raise ConsequenceError("only the one holding an obstacle can lift it")
        return s

    def _name(self, c: ConsequenceContext, actor_id: uuid.UUID) -> str:
        """How the player knows this person (the text is shown to the player)."""
        if actor_id == self._for(c):
            return "you"
        if actor_id in c.names:
            return c.names[actor_id]
        for x in c.cands:
            if x.id == str(actor_id):
                return x.known_as
        return c.names.get(actor_id, "someone")

    def _names(self, c: ConsequenceContext, ids: list[uuid.UUID]) -> str:
        return ", ".join(self._name(c, a) for a in ids)

    @staticmethod
    def _minutes(v: Any, default: int, lo: int, hi: int) -> int:
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            n = default
        return max(lo, min(hi, n))

    @staticmethod
    def _text(v: Any, limit: int = 120) -> str:
        t = re.sub(r"\s+", " ", str(v or "")).strip().strip('"')
        if not t:
            raise ConsequenceError("empty text")
        return t[:limit]

    def _amount(self, v: Any, hi: int = 12) -> int | str:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return max(1, min(hi, int(v)))
        s = str(v or "").strip()
        m = DICE_RE.match(s)
        if m:
            n = int(m.group(1) or 1)
            if n * int(m.group(2)) > hi * 2:
                raise ConsequenceError("too much at once")
            return s.replace(" ", "")
        if s.isdigit():
            return max(1, min(hi, int(s)))
        raise ConsequenceError(f"bad amount {v!r}")

    async def _now(self, c: ConsequenceContext) -> int:
        return await self.situations.now(c.h.timeline_id)

    # -- access and movement -------------------------------------------------------------------

    async def _k_grant_passage(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        s = await self._obstacle(c, p["obstacle"])
        who = (
            [c.actor_id]
            if str(p.get("who", "party")).lower() in ("actor", "self", "you")
            else await self._party(self._for(c))
        )
        passed = list(dict.fromkeys([*(s.data.get("passed") or []), *[str(a) for a in who]]))
        tx, e = await self._record(c, "grant_passage", p, f"{s.label}: passage for {len(who)}")
        await self.situations.change(tx, s, {"passed": passed}, cause=e)
        await self._done(tx)
        return Applied(
            "grant_passage",
            True,
            f"You may pass ({s.label}).",
            touched={str(s.id)},
        )

    async def _k_remove_obstacle(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        s = await self._obstacle(c, p["obstacle"])
        tx, e = await self._record(c, "remove_obstacle", p, s.label)
        await self.situations.close(tx, s, reason="removed", cause=e)
        await self._done(tx)
        return Applied(
            "remove_obstacle", True, f"No longer in the way: {s.label}.", touched={str(s.id)}
        )

    async def _k_add_obstacle(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        label = self._text(p["label"])
        blocks: list[str] = ["*"]
        if p.get("blocks") and str(p["blocks"]).lower() not in ("all", "*", "everywhere"):
            blocks = [self._place(c, p["blocks"]).id]
        holder = await self._one(c, p["held_by"]) if p.get("held_by") else None
        ways = [self._text(w, 60) for w in (p.get("ways_past") or []) if str(w).strip()][:3]
        minutes = self._minutes(
            p.get("minutes"), DEFAULT_OBSTACLE_SECONDS // 60, 5, MAX_OBSTACLE_SECONDS // 60
        )
        now = await self._now(c)
        tx, e = await self._record(c, "add_obstacle", p, label)
        s = await self.situations.open(
            tx,
            kind="obstacle",
            label=label,
            location_id=c.scene.location_id,
            holder_actor_id=holder,
            data={"blocks": blocks, "ways_past": ways or list(DEFAULT_WAYS_PAST), "passed": []},
            expires_tick=now + minutes * 60,
            cause=e,
            scene=c.scene,
        )
        await self._done(tx)
        return Applied("add_obstacle", True, f"In the way now: {label}.", touched={str(s.id)})

    async def _k_open_route(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        """A new way through is a small place of its own between here and there: going
        through it never passes the obstacles held here."""
        if c.scene.location_id is None:
            raise ConsequenceError("no place to open a way from")
        label = self._text(p["label"], 80)
        dest = self._place(c, p["to"])
        minutes = self._minutes(p.get("minutes"), 2, 1, 60)
        tx, e = await self._record(c, "open_route", p, f"{label} -> {dest.known_as}")
        await self._done(tx)
        path = await self.world.create_location(
            c.h,
            label[0].upper() + label[1:],
            location_type="path",
            detail_level="established",
            properties={"opened_by": str(c.actor_id), "leads_to": dest.id},
            metadata={"descriptor": label},
        )
        await self.world.connect_locations(
            c.h, c.scene.location_id, path.id, travel_seconds=30, relationship_type="path"
        )
        await self.world.connect_locations(
            c.h, path.id, uuid.UUID(dest.id), travel_seconds=minutes * 60, relationship_type="path"
        )
        from app.services.knowledge import KnowledgeService

        ks = KnowledgeService(self.session)
        ent = await self.session.get(Entity, path.entity_id)
        for a in await self._party(self._for(c)):
            await ks.learn_identity(c.h, a, path.entity_id, ent.canonical_name or label)  # type: ignore[union-attr]
        return Applied(
            "open_route",
            True,
            f"A way opens: {label}, leading to {dest.known_as}.",
            touched={str(path.id)},
        )

    async def _k_close_route(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        return await self._k_add_obstacle(
            c,
            {
                "label": p["label"],
                "blocks": p["to"],
                "ways_past": p.get("ways_past") or ["find another way round", "force it open"],
                "minutes": p.get("minutes", MAX_OBSTACLE_SECONDS // 60),
            },
        )

    async def _k_escort(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        dest = self._place(c, p["to"])
        who = await self._party(self._for(c))
        if p.get("by"):
            by = await self._one(c, p["by"])
            if by not in who:
                who.append(by)
        tx, e = await self._record(c, "escort", p, f"to {dest.known_as}")
        await self._done(tx)
        await self.scenes.travel(
            c.h, who, uuid.UUID(dest.id), created_by_type="engine", created_by_id=c.actor_id
        )
        return Applied(
            "escort", True, f"You are taken to {dest.known_as}.", touched={str(a) for a in who}
        )

    async def _k_reposition(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        zone = self._cand(c, p["zone"], ("zone",))
        if zone is None:
            raise ConsequenceError(f"unknown zone {p['zone']!r}")
        who = await self._person(c, p["who"])
        tx, e = await self._record(c, "reposition", p, zone.id)
        await self._done(tx)
        out = await self.actions.apply_effects(
            c.h,
            c.scene.id,
            source_key=str(c.actor_id),
            effects=[(str(a), [{"type": "move_entity", "params": {"zone": zone.id}}]) for a in who],
            description=f"moved to {zone.known_as}",
            turn_id=c.turn_id,
        )
        if out.status == "invalid":
            raise ConsequenceError(out.reason)
        return Applied(
            "reposition", True, f"{self._names(c, who).capitalize()} end up at {zone.known_as}."
        )

    # -- discovery -----------------------------------------------------------------------------

    async def _k_reveal_feature(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        text = self._text(p["description"], 120)
        tx, e = await self._record(c, "reveal_feature", p, text)
        await tx.emit(
            ev.CanonDetailEstablished(description=text, location_id=c.scene.location_id),
            cause=e,
            scene=c.scene,
            location_id=c.scene.location_id,
        )
        zone_key = None
        if p.get("zone"):
            z = self._cand(c, p["zone"], ("zone",))
            zone_key = z.id if z else None
        space = dict(c.scene.state.get("space") or {})
        zones = [dict(z) for z in space.get("zones", [])]
        mine = (space.get("positions", {}).get(str(c.actor_id)) or {}).get("zone")
        for z in zones:
            if z["key"] == (zone_key or mine):
                z["features"] = list(dict.fromkeys([*(z.get("features") or []), text]))
        if zones:
            fresh = await self.session.get(Scene, c.scene.id)
            fresh.state = {**fresh.state, "space": {**space, "zones": zones}}  # type: ignore[union-attr]
            tx.touch_scene(fresh)  # type: ignore[arg-type]
        await self._done(tx)
        return Applied("reveal_feature", True, f"You find: {text}.")

    async def _k_learn(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        """What the one acting now believes: a belief of their own, never a world fact."""
        from app.engine.beliefs import BeliefProposal, Proposition
        from app.services.knowledge import KnowledgeService

        text = self._text(p["text"], 200)
        # what is learned names nobody new (play session 3: a ruling "learned" the merchant's
        # name was Tomas, the companion's name); names come only from introduce
        known = {t.lower() for x in c.cands for t in re.findall(r"[A-Za-z']+", x.known_as)}
        known |= {t.lower() for n in c.names.values() for t in re.findall(r"[A-Za-z']+", n)}
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sent in sentences:
            for w in re.findall(r"\b[A-Z][a-z']+\b", sent)[1:] if sent else []:
                if w.lower() not in known:
                    raise ConsequenceError(f"learn may not name anyone or anything new ({w})")
        if re.search(r"\b(name is|named|called)\b", text, re.I):
            raise ConsequenceError("names are learned by introduce, not learn")
        tx, e = await self._record(c, "learn", p, text)
        prop = Proposition("learned", str(c.actor_id), None, text)
        formed = await tx.emit(
            ev.BeliefFormed(
                actor_id=c.actor_id,
                proposition_key=prop.key,
                belief_type="believed",
                confidence=0.75,
            ),
            cause=e,
        )
        await KnowledgeService(self.session).store_belief(
            tx,
            c.actor_id,
            BeliefProposal(prop, "believed", 0.75, "inferred", ("discovered by a check",)),
            acquired_event=formed,
        )
        await self._done(tx)
        return Applied("learn", True, f"You learn: {text}")

    async def _k_reveal_clue(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        from app.services.mystery import MysteryService

        ms = MysteryService(self.session)
        clue = await ms.clue_by_key(c.h.campaign_id, str(p["clue"]).strip())
        if clue is None:
            raise ConsequenceError(f"unknown clue {p['clue']!r}")
        tx, e = await self._record(c, "reveal_clue", p, str(p["clue"]))
        found = await ms.discover(tx, clue, c.actor_id, route="mechanic", cause=e)
        await self._done(tx)
        if found is None:
            raise ConsequenceError("that clue can no longer be found")
        return Applied("reveal_clue", True, "You find something that matters.")

    async def _k_reveal_item(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        tx, e = await self._record(c, "reveal_item", p, "concealed things here")
        await self._done(tx)
        out = await self.actions.apply_effects(
            c.h,
            c.scene.id,
            source_key=str(c.actor_id),
            effects=[],
            reveal_for=str(c.actor_id),
            description="something concealed is found",
            turn_id=c.turn_id,
        )
        names = [x.get("name") for x in out.events if x.get("type") == "item.revealed"]
        if not names:
            return Applied("reveal_item", True, "There is nothing hidden here after all.")
        return Applied("reveal_item", True, "You find: " + ", ".join(str(n) for n in names) + ".")

    async def _k_introduce(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        """The person's name becomes known to everyone in the acting party present."""
        person = await self._one(c, p["person"])
        actor = await self.session.get(Actor, person)
        ent = await self.session.get(Entity, actor.entity_id) if actor else None
        if ent is None or not ent.canonical_name:
            raise ConsequenceError("they have no name to give")
        tx, e = await self._record(c, "introduce", p, ent.canonical_name)
        from app.services.knowledge import KnowledgeService

        ks = KnowledgeService(self.session)
        listeners = await self._party(self._for(c))
        for a in listeners:
            if a != person:
                await ks.learn_identity(c.h, a, ent.id, ent.canonical_name, tx=tx, cause=e)
        await self._done(tx)
        return Applied("introduce", True, f"You learn their name: {ent.canonical_name}.")

    # -- people --------------------------------------------------------------------------------

    async def _k_change_attitude(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        from app.services.psychology import PsychologyService

        person = await self._one(c, p["person"])
        dim = str(p["dimension"]).lower().strip()
        if dim not in DIMENSIONS:
            raise ConsequenceError(f"unknown feeling {dim!r}")
        try:
            steps = max(-2, min(2, int(float(p["delta"]))))
        except (TypeError, ValueError) as exc:
            raise ConsequenceError("delta must be a number") from exc
        if steps == 0:
            raise ConsequenceError("no change")
        toward = (
            await self._party(self._for(c))
            if str(p.get("toward", "")).lower() == "party"
            else [await self._one(c, p["toward"]) if p.get("toward") else self._for(c)]
        )
        tx, e = await self._record(c, "change_attitude", p, f"{dim} {steps:+d}")
        psy = PsychologyService(self.session)
        for t in toward:
            if t == person:
                continue
            target = await self.session.get(Actor, t)
            await psy.apply_relationship_delta(
                tx,
                person,
                target.entity_id,
                dim,
                steps * ATTITUDE_STEP,
                reason="consequence",
                cause=e,  # type: ignore[union-attr]
            )
        await self._done(tx)
        word = {"trust": "trusts", "respect": "respects", "affection": "likes", "fear": "fears"}[
            dim
        ]
        how = "more" if steps > 0 else "less"
        return Applied(
            "change_attitude",
            True,
            f"{self._name(c, person).capitalize()} {word} {self._names(c, toward)} {how}.",
        )

    async def _commitment(
        self, c: ConsequenceContext, kind: str, p: dict[str, Any], *, refused: bool
    ) -> Applied:
        person = await self._one(c, p["person"])
        request = self._text(p["request"], 160)
        data: dict[str, Any] = {"for": [str(a) for a in await self._party(self._for(c))]}
        if refused:
            data["refused"] = True
        lets: Situation | None = None
        if p.get("lets_pass") and not refused:
            lets = await self.situations.resolve_ref(
                [x for x in await self._visible(c) if x.kind == "obstacle"], p["lets_pass"]
            )
            if lets is not None and lets.holder_actor_id == person:
                data["lets_pass"] = str(lets.id)
        tx, e = await self._record(c, kind, p, request)
        await self.situations.open(
            tx,
            kind="commitment",
            label=("refused: " if refused else "") + request,
            subject_actor_id=person,
            location_id=None,
            data=data,
            cause=e,
            scene=c.scene,
        )
        if not refused and ESCORT_RE.search(request):
            # an agreed escort ties the groups: whoever travels, both go (DECISIONS 10e)
            await self.situations.open(
                tx,
                kind="follower",
                label="travelling with the party",
                subject_actor_id=person,
                data={"with": str(self._for(c)), "linked": True},
                expires_tick=(await self._now(c)) + 6 * 3600,
                cause=e,
                scene=c.scene,
            )
        await self._done(tx)
        who = self._name(c, person).capitalize()
        return Applied(
            kind,
            True,
            f"{who} refuses: {request}." if refused else f"{who} agrees: {request}.",
            touched={str(lets.id)} if lets is not None else set(),
        )

    async def _k_agree(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        return await self._commitment(c, "agree", p, refused=False)

    async def _k_refuse(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        return await self._commitment(c, "refuse", p, refused=True)

    async def _k_accompany(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        person = await self._one(c, p["person"])
        minutes = self._minutes(p.get("minutes"), 180, 10, 24 * 60)
        now = await self._now(c)
        tx, e = await self._record(c, "accompany", p, str(person))
        await self.situations.open(
            tx,
            kind="follower",
            label="accompanying the party",
            subject_actor_id=person,
            data={"with": str(self._for(c)), "linked": True},
            expires_tick=now + minutes * 60,
            cause=e,
            scene=c.scene,
        )
        await self._done(tx)
        return Applied(
            "accompany", True, f"{self._name(c, person).capitalize()} comes along with you."
        )

    async def _k_leave(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        person = await self._one(c, p["person"])
        if person == c.actor_id:
            raise ConsequenceError("the one acting leaves by travelling")
        if p.get("to"):
            dest = self._place(c, p["to"])
        else:
            exits = [x for x in c.cands if x.kind == "location"]
            if not exits:
                raise ConsequenceError("nowhere to go")
            dest = exits[0]
        tx, e = await self._record(c, "leave", p, dest.known_as)
        await self._done(tx)
        await self.scenes.travel(
            c.h, [person], uuid.UUID(dest.id), created_by_type="engine", created_by_id=person
        )
        return Applied(
            "leave", True, f"{self._name(c, person).capitalize()} leaves.", touched={str(person)}
        )

    async def _status(
        self,
        c: ConsequenceContext,
        kind: str,
        who: list[uuid.UUID],
        label: str,
        minutes: int | None,
        data: dict[str, Any] | None = None,
    ) -> None:
        now = await self._now(c)
        tx, e = await self._record(c, kind, {"status": label}, label)
        for a in who:
            existing = await self.situations.status_of(a, label)
            if existing is not None:
                continue
            await self.situations.open(
                tx,
                kind="status",
                label=label,
                subject_actor_id=a,
                data=dict(data or {}),
                expires_tick=(now + minutes * 60) if minutes else None,
                cause=e,
                scene=c.scene,
            )
        await self._done(tx)

    async def _k_distract(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        person = await self._one(c, p["person"])
        minutes = self._minutes(p.get("minutes"), 10, 1, 60)
        await self._status(c, "distract", [person], "distracted", minutes, {"distracted": True})
        return Applied("distract", True, f"{self._name(c, person).capitalize()} is distracted.")

    async def _k_turn_hostile(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        person = await self._one(c, p["person"])
        await self._status(c, "turn_hostile", [person], "hostile", None, {"hostile": True})
        res = await self._k_change_attitude(
            c,
            {
                "person": p["person"],
                "toward": p.get("toward", "party"),
                "dimension": "trust",
                "delta": -2,
            },
        )
        if not res.ok:
            pass
        return Applied("turn_hostile", True, f"{self._name(c, person).capitalize()} turns hostile.")

    async def _k_raise_alarm(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        text = self._text(p["text"], 100)
        now = await self._now(c)
        tx, e = await self._record(c, "raise_alarm", p, text)
        await self.situations.open(
            tx,
            kind="alarm",
            label=text,
            location_id=c.scene.location_id,
            data={"raised_by": str(c.proposer_id or c.actor_id)},
            expires_tick=now + 2 * 3600,
            cause=e,
            scene=c.scene,
        )
        await self._done(tx)
        return Applied("raise_alarm", True, f"The alarm is raised: {text}.")

    async def _k_owe_favor(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        debtor = await self._one(c, p["debtor"])
        creditor = await self._one(c, p["creditor"])
        what = self._text(p["what"], 120)
        tx, e = await self._record(c, "owe_favor", p, what)
        await self.situations.open(
            tx,
            kind="debt",
            label=f"{what} (to {self._name(c, creditor)})",
            subject_actor_id=debtor,
            data={"creditor": str(creditor), "what": what},
            cause=e,
            scene=c.scene,
        )
        await self._done(tx)
        return Applied(
            "owe_favor",
            True,
            f"{self._name(c, debtor).capitalize()} owes {self._name(c, creditor)}: {what}.",
        )

    # -- status --------------------------------------------------------------------------------

    async def _k_set_status(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        who = await self._person(c, p["who"])
        label = self._text(p["status"], 40).lower()
        minutes = self._minutes(p["minutes"], 60, 1, 7 * 24 * 60) if p.get("minutes") else None
        await self._status(c, "set_status", who, label, minutes)
        return Applied("set_status", True, f"{self._names(c, who).capitalize()}: {label}.")

    async def _k_clear_status(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        who = await self._person(c, p["who"])
        label = self._text(p["status"], 40).lower()
        closed = 0
        tx, e = await self._record(c, "clear_status", p, label)
        for a in who:
            s = await self.situations.status_of(a, label)
            if s is not None:
                await self.situations.close(tx, s, reason="cleared", cause=e)
                closed += 1
        await self._done(tx)
        if not closed:
            raise ConsequenceError(f"nobody had the status {label!r}")
        return Applied("clear_status", True, f"No longer {label}: {self._names(c, who)}.")

    async def _k_advance_clock(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        name = self._text(p["name"], 40)
        by = self._minutes(p.get("by"), 1, 1, 2)
        now = await self._now(c)
        existing = next(
            (
                s
                for s in await self.situations.at_location(
                    c.h.campaign_id, c.scene.location_id, now
                )
                if s.kind == "clock" and s.label.lower() == name.lower()
            ),
            None,
        )
        tx, e = await self._record(c, "advance_clock", p, name)
        if existing is None:
            of = self._minutes(p.get("of"), 4, 3, 8)
            s = await self.situations.open(
                tx,
                kind="clock",
                label=name,
                location_id=c.scene.location_id,
                data={"value": min(by, of), "of": of, "full": by >= of},
                cause=e,
                scene=c.scene,
            )
        else:
            s = existing
            of = int(s.data.get("of", 4))
            value = min(of, int(s.data.get("value", 0)) + by)
            await self.situations.change(tx, s, {"value": value, "full": value >= of}, cause=e)
        await self._done(tx)
        full = " It is full." if s.data.get("full") else ""
        return Applied(
            "advance_clock", True, f"{name}: {s.data.get('value')}/{s.data.get('of')}.{full}"
        )

    # -- items and coin ------------------------------------------------------------------------

    async def _k_pay(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        payer = await self._one(c, p["from"])
        payee = await self._one(c, p["to"])
        try:
            amount = max(1, min(1000, int(float(p["amount"]))))
        except (TypeError, ValueError) as exc:
            raise ConsequenceError("amount must be a number of coins") from exc
        if payer == payee:
            raise ConsequenceError("paying oneself")
        await self.pay(c, payer, payee, amount)
        return Applied(
            "pay",
            True,
            f"{self._name(c, payer).capitalize()} pays {self._name(c, payee)} {amount} coin.",
        )

    async def pay(
        self, c: ConsequenceContext, payer: uuid.UUID, payee: uuid.UUID, amount: int
    ) -> None:
        loaded = await self.actions.load_scene(c.h, c.scene.id)
        st = loaded.ctx.states.get(str(payer))
        if st is None or str(payee) not in loaded.ctx.states:
            raise ConsequenceError("they are not both here")
        have = st.resources.get("resource.coin")
        if have is None or have.current < amount:
            raise ConsequenceError("not enough coin")
        tx, e = await self._record(c, "pay", {"amount": amount}, f"{amount} coin")
        await self._done(tx)
        out = await self.actions.apply_effects(
            c.h,
            c.scene.id,
            source_key=str(payer),
            effects=[
                (
                    str(payer),
                    [
                        {
                            "type": "modify_resource",
                            "params": {"resource": "resource.coin", "amount": -amount},
                        }
                    ],
                ),
                (
                    str(payee),
                    [
                        {
                            "type": "modify_resource",
                            "params": {"resource": "resource.coin", "amount": amount},
                        }
                    ],
                ),
            ],
            description=f"pays {amount} coin",
            turn_id=c.turn_id,
        )
        if out.status == "invalid":
            raise ConsequenceError(out.reason)

    async def _k_give_item(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        from app.persistence.models import Item, ItemHistory

        giver = await self._one(c, p["from"])
        taker = await self._one(c, p["to"])
        giver_actor = await self.session.get(Actor, giver)
        taker_actor = await self.session.get(Actor, taker)
        cand = self._cand(c, p["item"], ("item",))
        rows = (
            await self.session.execute(
                select(Item, Entity)
                .join(Entity, Entity.id == Item.entity_id)
                .where(
                    Item.possessor_entity_id == giver_actor.entity_id,  # type: ignore[union-attr]
                    Item.destroyed_event_id.is_(None),
                )
            )
        ).all()
        want = _tokens(str(cand.known_as if cand else p["item"]))
        hit = None
        for item, ent in rows:
            if (cand is not None and cand.id == str(item.id)) or (
                want and want <= _tokens(ent.canonical_name or item.template_key or "")
            ):
                hit = (item, ent)
                break
        if hit is None:
            raise ConsequenceError(f"{self._name(c, giver)} has no {p['item']!r}")
        item, ent = hit
        tx, e = await self._record(c, "give_item", p, ent.canonical_name or "item")
        item.possessor_entity_id = taker_actor.entity_id  # type: ignore[union-attr]
        item.owner_entity_id = taker_actor.entity_id  # type: ignore[union-attr]
        self.session.add(
            ItemHistory(
                item_id=item.id,
                event_id=e.id,
                change_type="transferred",
                payload={"from": str(giver), "to": str(taker)},
            )
        )
        await self._done(tx)
        return Applied(
            "give_item",
            True,
            f"{self._name(c, giver).capitalize()} gives "
            f"{self._name(c, taker)} {ent.canonical_name}.",
        )

    async def _k_create_item(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        name = self._text(p["name"], 60)
        holder = None
        if p.get("holder") and str(p["holder"]).lower() not in ("here", "ground", "scene"):
            holder = await self._one(c, p["holder"])
        tx, e = await self._record(c, "create_item", p, name)
        await self._done(tx)
        zone = None
        if holder is None:
            zone = (
                (c.scene.state.get("space") or {}).get("positions", {}).get(str(c.actor_id)) or {}
            ).get("zone")
        await self.world.create_item(
            c.h,
            name,
            template_key=None,
            possessor_actor_id=holder,
            location_id=None if holder else c.scene.location_id,
            zone_key=zone,
            public_properties={"description": str(p.get("description") or "")[:200]},
            provenance={"consequence": True, "by": str(c.actor_id)},
        )
        where = f"{self._name(c, holder)} now has" if holder else "Here now:"
        return Applied("create_item", True, f"{where.capitalize() if holder else where} {name}.")

    async def _k_destroy_item(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        cand = self._cand(c, p["item"], ("item",))
        if cand is None:
            raise ConsequenceError(f"unknown item {p['item']!r}")
        try:
            item_id = uuid.UUID(cand.id)
        except ValueError as exc:
            raise ConsequenceError("that item cannot be destroyed this way") from exc
        tx, e = await self._record(c, "destroy_item", p, cand.known_as)
        await self.world.destroy_item(c.h, item_id, reason="consequence", tx=tx, cause=e)
        await self._done(tx)
        return Applied("destroy_item", True, f"Ruined: {cand.known_as}.")

    async def _k_set_price(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        seller = await self._one(c, p["seller"])
        try:
            pct = max(-50, min(100, int(float(p["percent"]))))
        except (TypeError, ValueError) as exc:
            raise ConsequenceError("percent must be a number") from exc
        tx, e = await self._record(c, "set_price", p, f"{pct:+d}%")
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == seller,
                        Situation.kind == "price",
                        Situation.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        for old in rows:
            await self.situations.close(tx, old, reason="new price", cause=e)
        label = "discount" if pct < 0 else "markup"
        await self.situations.open(
            tx,
            kind="price",
            label=f"{abs(pct)}% {label} for the party",
            subject_actor_id=seller,
            data={"percent": pct, "for": [str(a) for a in await self._party(self._for(c))]},
            cause=e,
            scene=c.scene,
        )
        await self._done(tx)
        return Applied(
            "set_price", True, f"{self._name(c, seller).capitalize()}: {abs(pct)}% {label}."
        )

    # -- body and time -------------------------------------------------------------------------

    async def _effects_on(
        self,
        c: ConsequenceContext,
        kind: str,
        p: dict[str, Any],
        steps: list[dict[str, Any]],
        text: str,
    ) -> Applied:
        who = await self._person(c, p["who"])
        tx, e = await self._record(c, kind, p, text)
        await self._done(tx)
        out = await self.actions.apply_effects(
            c.h,
            c.scene.id,
            source_key=str(c.proposer_id or c.actor_id),
            effects=[(str(a), steps) for a in who],
            description=text,
            turn_id=c.turn_id,
        )
        if out.status == "invalid":
            raise ConsequenceError(out.reason)
        return Applied(kind, True, f"{self._names(c, who).capitalize()}: {text}.")

    async def _k_harm(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        amt = self._amount(p["amount"])
        return await self._effects_on(
            c, "harm", p, [{"type": "deal_damage", "params": {"amount": amt}}], "hurt"
        )

    async def _k_heal(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        amt = self._amount(p["amount"])
        return await self._effects_on(
            c,
            "heal",
            p,
            [
                {
                    "type": "restore_resource",
                    "params": {"resource": "resource.health", "amount": amt},
                }
            ],
            "recovers",
        )

    async def _k_condition(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        key = str(p["condition"]).strip().lower()
        if not key.startswith("condition."):
            key = "condition." + key.replace(" ", "_")
        cdef = self.engine.ruleset.conditions.get(key)
        if cdef is None or key in ("condition.incapacitated",):
            raise ConsequenceError(f"not an allowed condition {p['condition']!r}")
        params: dict[str, Any] = {"condition": key}
        if p.get("minutes"):
            params["duration_seconds"] = self._minutes(p["minutes"], 10, 1, 24 * 60) * 60
        return await self._effects_on(
            c, "condition", p, [{"type": "apply_condition", "params": params}], cdef.name.lower()
        )

    async def _k_pass_time(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        minutes = self._minutes(p["minutes"], 10, 1, 240)
        tx, e = await self._record(c, "pass_time", p, f"{minutes} min")
        await self._done(tx)
        await self.world.advance_time(c.h, minutes * 60, reason="consequence", scene_id=c.scene.id)
        return Applied("pass_time", True, f"{minutes} minutes pass.")

    async def _k_schedule(self, c: ConsequenceContext, p: dict[str, Any]) -> Applied:
        from app.services.schedule import ScheduleService

        minutes = self._minutes(p["minutes"], 30, 5, 24 * 60)
        what = self._text(p["what"], 160)
        tx, e = await self._record(c, "schedule", p, what)
        await ScheduleService(self.session).schedule(
            c.h,
            tick=(await self._now(c)) + minutes * 60,
            event_type="narrative.note",
            payload={"text": what, "location_id": str(c.scene.location_id or "")},
            tx=tx,
        )
        await self._done(tx)
        return Applied("schedule", True, "")  # the player does not learn what is coming

    # -- the engine's safety net ---------------------------------------------------------------

    async def safety_net(
        self,
        c: ConsequenceContext,
        *,
        succeeded: bool,
        target_actor: uuid.UUID | None,
        addresses: str | None,
        applied: list[Applied],
        social_kind: str | None = None,
        text: str = "",
    ) -> list[Applied]:
        """No soft-blocks (DECISIONS 10d): a success aimed at an obstacle, or at someone holding
        one that stops the party, that resolved nothing grants the party passage; a social
        success that changed nothing shifts the listener's attitude."""
        if not succeeded:
            return []
        out: list[Applied] = []
        resolved = set().union(*(a.touched for a in applied if a.ok)) if applied else set()
        sits = [s for s in await self._visible(c) if s.kind == "obstacle"]
        aimed = await self.situations.resolve_ref(sits, addresses) if addresses else None
        held = [s for s in sits if target_actor is not None and s.holder_actor_id == target_actor]
        for s in [x for x in [aimed, *held] if x is not None]:
            if str(s.id) in resolved:
                continue
            if any(str(a) in (s.data.get("passed") or []) for a in [c.actor_id]):
                continue
            from app.services.situations import sref

            out.append(
                await self.apply_one(c, "grant_passage", {"obstacle": sref(s), "who": "party"})
            )
            resolved.add(str(s.id))
        haggling = re.search(
            r"(haggle|haggling|price|cheaper|discount|deal|bargain|less|lower)", text.lower()
        )
        if (
            social_kind == "persuade"
            and haggling
            and target_actor is not None
            and not any(a.ok and a.kind == "set_price" for a in applied)
        ):
            cand = next((x for x in c.cands if x.id == str(target_actor)), None)
            if cand is not None:
                out.append(
                    await self.apply_one(c, "set_price", {"seller": cand.ref, "percent": -15})
                )
        if social_kind and target_actor is not None and not any(a.ok for a in applied) and not out:
            dim = {"intimidate": "fear", "perform": "affection"}.get(social_kind, "trust")
            cand = next((x for x in c.cands if x.id == str(target_actor)), None)
            if cand is not None:
                out.append(
                    await self.apply_one(
                        c,
                        "change_attitude",
                        {"person": cand.ref, "toward": "you", "dimension": dim, "delta": 1},
                    )
                )
        return out
