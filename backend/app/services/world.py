"""WorldService — objective-world foundations (Milestone 01).

Creates campaigns, locations, topology, actors, scenes; moves actors; advances time. Every
mutation goes through `EventTransaction` so the ledger explains every projection.

This service works on **objective truth**. Nothing here is perspective-filtered; from
Milestone 03, actor-facing reads go through `PerspectiveService` instead.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.persistence.models import (
    Actor,
    ActorController,
    Campaign,
    Document,
    Entity,
    Event,
    Faction,
    FactionMembership,
    Item,
    ItemHistory,
    Location,
    LocationEdge,
    Party,
    PartyMembership,
    Scene,
    SceneParticipant,
    Timeline,
    WorldClock,
)
from app.services.events import EventTransaction

CONTROLLER_TYPES = {"human", "ai", "scripted", "dormant"}


class WorldError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignHandle:
    campaign_id: uuid.UUID
    timeline_id: uuid.UUID


class WorldService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- helpers -------------------------------------------------------------------------------

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    async def _get(self, model: type, id_: uuid.UUID, *, what: str) -> Any:
        obj = await self.session.get(model, id_)
        if obj is None:
            raise WorldError(f"{what} {id_} not found")
        return obj

    async def _active_controller(self, actor_id: uuid.UUID) -> ActorController | None:
        return (
            await self.session.execute(
                select(ActorController).where(
                    ActorController.actor_id == actor_id,
                    ActorController.valid_until_event_id.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def _active_participation(self, actor_id: uuid.UUID) -> SceneParticipant | None:
        return (
            await self.session.execute(
                select(SceneParticipant).where(
                    SceneParticipant.actor_id == actor_id,
                    SceneParticipant.left_event_id.is_(None),
                )
            )
        ).scalar_one_or_none()

    # -- campaign ------------------------------------------------------------------------------

    async def create_campaign(
        self,
        name: str,
        *,
        ruleset_key: str,
        ruleset_version: str,
        engine_version: str,
        creation_mode: str = "manual",
        campaign_mode: str = "sandbox",
        settings: dict[str, Any] | None = None,
        calendar_definition: dict[str, Any] | None = None,
    ) -> CampaignHandle:
        s = self.session
        if not s.in_transaction():
            await s.begin()
        campaign = Campaign(
            name=name,
            status="draft",
            creation_mode=creation_mode,
            campaign_mode=campaign_mode,
            ruleset_key=ruleset_key,
            ruleset_version=ruleset_version,
            engine_version=engine_version,
            settings=settings or {},
        )
        s.add(campaign)
        await s.flush()
        timeline = Timeline(campaign_id=campaign.id, name="main")
        s.add(timeline)
        await s.flush()
        s.add(WorldClock(timeline_id=timeline.id, calendar_definition=calendar_definition or {}))
        campaign.active_timeline_id = timeline.id
        await s.flush()
        handle = CampaignHandle(campaign.id, timeline.id)
        async with self._tx(handle) as tx:
            await tx.emit(
                ev.CampaignCreated(
                    name=name, ruleset_key=ruleset_key, ruleset_version=ruleset_version
                )
            )
        return handle

    # -- locations -----------------------------------------------------------------------------

    async def create_location(
        self,
        h: CampaignHandle,
        name: str,
        *,
        location_type: str = "other",
        parent_location_id: uuid.UUID | None = None,
        detail_level: str = "materialized",
        importance_tier: str = "standard",
        properties: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        simulation_state: dict[str, Any] | None = None,
    ) -> Location:
        async with self._tx(h) as tx:
            entity = Entity(
                campaign_id=h.campaign_id,
                entity_type="location",
                canonical_name=name,
                importance_tier=importance_tier,
                metadata_=metadata or {},
            )
            self.session.add(entity)
            await self.session.flush()
            location = Location(
                entity_id=entity.id,
                parent_location_id=parent_location_id,
                location_type=location_type,
                detail_level=detail_level,
                properties=properties or {},
                simulation_state=simulation_state or {},
            )
            self.session.add(location)
            await self.session.flush()
            event = await tx.emit(
                ev.LocationCreated(
                    location_id=location.id,
                    entity_id=entity.id,
                    name=name,
                    location_type=location_type,
                    parent_location_id=parent_location_id,
                ),
                location_id=location.id,
                entities=[(entity.id, "subject")],
            )
            entity.created_event_id = event.id
            if detail_level == "established":
                entity.established_event_id = event.id
        return location

    async def connect_locations(
        self,
        h: CampaignHandle,
        from_location_id: uuid.UUID,
        to_location_id: uuid.UUID,
        *,
        relationship_type: str = "connected",
        travel_seconds: int | None = None,
        bidirectional: bool = True,
        requirements: dict[str, Any] | None = None,
    ) -> list[LocationEdge]:
        async with self._tx(h) as tx:
            pairs = [(from_location_id, to_location_id)]
            if bidirectional:
                pairs.append((to_location_id, from_location_id))
            edges: list[LocationEdge] = []
            for a, b in pairs:
                edge = LocationEdge(
                    campaign_id=h.campaign_id,
                    from_location_id=a,
                    to_location_id=b,
                    relationship_type=relationship_type,
                    travel_seconds=travel_seconds,
                    requirements=requirements or {},
                )
                self.session.add(edge)
                edges.append(edge)
            await self.session.flush()
            event = await tx.emit(
                ev.LocationsConnected(
                    edge_id=edges[0].id,
                    from_location_id=from_location_id,
                    to_location_id=to_location_id,
                    relationship_type=relationship_type,
                    travel_seconds=travel_seconds,
                    bidirectional=bidirectional,
                )
            )
            for edge in edges:
                edge.created_event_id = event.id
        return edges

    async def find_edge(
        self, from_location_id: uuid.UUID, to_location_id: uuid.UUID
    ) -> LocationEdge | None:
        return (
            (
                await self.session.execute(
                    select(LocationEdge).where(
                        LocationEdge.from_location_id == from_location_id,
                        LocationEdge.to_location_id == to_location_id,
                    )
                )
            )
            .scalars()
            .first()
        )

    # -- actors --------------------------------------------------------------------------------

    async def create_actor(
        self,
        h: CampaignHandle,
        name: str,
        *,
        actor_type: str = "npc",
        controller_type: str = "ai",
        user_key: str | None = None,
        location_id: uuid.UUID | None = None,
        importance_tier: str = "standard",
        mechanical_profile: dict[str, Any] | None = None,
        behavior_profile: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Actor:
        if controller_type not in CONTROLLER_TYPES:
            raise WorldError(f"invalid controller_type {controller_type!r}")
        async with self._tx(h) as tx:
            entity = Entity(
                campaign_id=h.campaign_id,
                entity_type="actor",
                canonical_name=name,
                importance_tier=importance_tier,
                metadata_=metadata or {},
            )
            self.session.add(entity)
            await self.session.flush()
            actor = Actor(
                entity_id=entity.id,
                actor_type=actor_type,
                importance_tier=importance_tier,
                current_location_id=location_id,
                mechanical_profile=mechanical_profile or {},
                behavior_profile=behavior_profile or {},
            )
            self.session.add(actor)
            await self.session.flush()
            event = await tx.emit(
                ev.ActorCreated(
                    actor_id=actor.id,
                    entity_id=entity.id,
                    name=name,
                    actor_type=actor_type,
                    controller_type=controller_type,
                    location_id=location_id,
                ),
                location_id=location_id,
                entities=[(entity.id, "subject")],
            )
            entity.created_event_id = event.id
            actor.updated_event_id = event.id
            self.session.add(
                ActorController(
                    actor_id=actor.id,
                    controller_type=controller_type,
                    user_key=user_key,
                    valid_from_event_id=event.id,
                )
            )
        return actor

    async def set_controller(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        controller_type: str,
        *,
        user_key: str | None = None,
    ) -> ActorController:
        """Switch who drives an actor. Changes only control history (Invariant 11)."""
        if controller_type not in CONTROLLER_TYPES:
            raise WorldError(f"invalid controller_type {controller_type!r}")
        async with self._tx(h) as tx:
            actor = await self._get(Actor, actor_id, what="actor")
            current = await self._active_controller(actor_id)
            if current is None:
                raise WorldError(f"actor {actor_id} has no active controller")
            event = await tx.emit(
                ev.ActorControllerChanged(
                    actor_id=actor_id,
                    from_controller=current.controller_type,
                    to_controller=controller_type,
                    user_key=user_key,
                ),
                entities=[(actor.entity_id, "subject")],
            )
            current.valid_until_event_id = event.id
            await self.session.flush()  # release the partial unique index before inserting
            new = ActorController(
                actor_id=actor_id,
                controller_type=controller_type,
                user_key=user_key,
                valid_from_event_id=event.id,
            )
            self.session.add(new)
        return new

    async def move_actor(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        to_location_id: uuid.UUID,
        *,
        travel_seconds: int | None = None,
        require_edge: bool = False,
    ) -> Event:
        """Relocate an actor. Leaves any active scene at a different location.

        If `travel_seconds` is given (or derived from the edge when `require_edge`), a
        `time.advanced` event is emitted in the same transaction with the move as its cause.
        """
        async with self._tx(h) as tx:
            actor = await self._get(Actor, actor_id, what="actor")
            await self._get(Location, to_location_id, what="location")
            from_location_id = actor.current_location_id
            if require_edge:
                if from_location_id is None:
                    raise WorldError("actor has no current location")
                edge = await self.find_edge(from_location_id, to_location_id)
                if edge is None:
                    raise WorldError("no edge between locations")
                if travel_seconds is None:
                    travel_seconds = edge.travel_seconds
            left_scene_id: uuid.UUID | None = None
            participation = await self._active_participation(actor_id)
            scene: Scene | None = None
            if participation is not None:
                scene = await self._get(Scene, participation.scene_id, what="scene")
                if scene.location_id != to_location_id:
                    left_scene_id = scene.id
                else:
                    scene = None
            move = await tx.emit(
                ev.ActorMoved(
                    actor_id=actor_id,
                    from_location_id=from_location_id,
                    to_location_id=to_location_id,
                    left_scene_id=left_scene_id,
                ),
                scene=scene,
                location_id=to_location_id,
                entities=[(actor.entity_id, "subject")],
            )
            actor.current_location_id = to_location_id
            actor.updated_event_id = move.id
            if left_scene_id is not None and participation is not None and scene is not None:
                participation.left_event_id = move.id
                actor.current_scene_id = None
                await tx.emit(
                    ev.SceneParticipantLeft(scene_id=scene.id, actor_id=actor_id),
                    scene=scene,
                    cause=move,
                    entities=[(actor.entity_id, "subject")],
                )
            if travel_seconds:
                await self._advance_clock(tx, travel_seconds, reason="travel", cause=move)
        return move

    # -- items ---------------------------------------------------------------------------------

    async def create_item(
        self,
        h: CampaignHandle,
        name: str,
        *,
        template_key: str | None,
        possessor_actor_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        zone_key: str | None = None,
        owner_actor_id: uuid.UUID | None = None,
        equipped: bool = True,
        public_properties: dict[str, Any] | None = None,
        hidden_properties: dict[str, Any] | None = None,
        importance_tier: str = "standard",
        item_type: str = "gear",
        provenance: dict[str, Any] | None = None,
        concealed: bool = False,
        concealment_difficulty: str | None = None,
        document: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Item:
        """A unique persistent item (world-memory §15). Ownership and possession are distinct;
        hidden properties exist objectively from creation (rules-engine §22).

        `concealed` items lie in a location zone unseen until a successful search reveals them
        (`concealment_difficulty` names a ruleset difficulty the search total must meet).
        `document` = {text, conveys, author_entity_id?, language?} makes the item an immutable
        Document (world-memory §15; c&k §3) in the same transaction."""
        if concealed and (location_id is None or possessor_actor_id is not None):
            raise WorldError("only an item lying in a location can be concealed")
        async with self._tx(h) as tx:
            possessor_entity = owner_entity = None
            if possessor_actor_id is not None:
                possessor_entity = (
                    await self._get(Actor, possessor_actor_id, what="actor")
                ).entity_id
            if owner_actor_id is not None:
                owner_entity = (await self._get(Actor, owner_actor_id, what="actor")).entity_id
            entity = Entity(
                campaign_id=h.campaign_id,
                entity_type="item",
                canonical_name=name,
                importance_tier=importance_tier,
                metadata_=metadata or {},
            )
            self.session.add(entity)
            await self.session.flush()
            snapshot: dict[str, Any] = {"equipped": equipped and possessor_entity is not None}
            if concealment_difficulty:
                snapshot["concealment_difficulty"] = concealment_difficulty
            item = Item(
                entity_id=entity.id,
                template_key=template_key,
                item_type="document" if document is not None else item_type,
                mechanical_snapshot=snapshot,
                concealed=concealed,
                owner_entity_id=owner_entity or possessor_entity,
                possessor_entity_id=possessor_entity,
                location_id=location_id if possessor_entity is None else None,
                zone_key=zone_key if possessor_entity is None else None,
                public_properties=public_properties or {},
                hidden_properties=hidden_properties or {},
                provenance=provenance or {},
            )
            self.session.add(item)
            await self.session.flush()
            event = await tx.emit(
                ev.ItemCreated(
                    item_id=item.id,
                    entity_id=entity.id,
                    name=name,
                    template_key=template_key,
                    possessor_actor_id=possessor_actor_id,
                    location_id=location_id,
                ),
                location_id=location_id,
                entities=[(entity.id, "subject")],
            )
            entity.created_event_id = event.id
            item.created_event_id = event.id
            if document is not None:
                text = str(document["text"])
                self.session.add(
                    Document(
                        item_id=item.id,
                        original_text=text,
                        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        author_entity_id=document.get("author_entity_id"),
                        creation_tick=document.get("creation_tick"),
                        language=document.get("language", "common"),
                        cipher=document.get("cipher"),
                        conveys=list(document.get("conveys", [])),
                    )
                )
                await self.session.flush()
        return item

    async def destroy_item(
        self,
        h: CampaignHandle,
        item_id: uuid.UUID,
        *,
        reason: str = "",
        tx: EventTransaction | None = None,
        cause: Event | None = None,
    ) -> Item:
        """Remove an item from the world. Its history stays; the row records the destroying
        event (world-memory §15: unique items keep a history)."""
        if tx is None:
            async with self._tx(h) as tx2:
                return await self.destroy_item(h, item_id, reason=reason, tx=tx2, cause=cause)
        item = await self._get(Item, item_id, what="item")
        if item.destroyed_event_id is not None:
            return item
        event = await tx.emit(
            ev.ItemDestroyed(item_id=item.id, reason=reason),
            cause=cause,
            entities=[(item.entity_id, "subject")],
        )
        item.destroyed_event_id = event.id
        item.possessor_entity_id, item.location_id, item.zone_key = None, None, None
        self.session.add(
            ItemHistory(
                item_id=item.id,
                event_id=event.id,
                change_type="destroyed",
                payload={"reason": reason},
            )
        )
        ent = await self._get(Entity, item.entity_id, what="entity")
        ent.lifecycle_state = "destroyed"
        return item

    # -- scenes --------------------------------------------------------------------------------

    async def start_scene(
        self,
        h: CampaignHandle,
        *,
        location_id: uuid.UUID | None,
        scene_type: str = "social",
        participant_actor_ids: list[uuid.UUID] | None = None,
        state: dict[str, Any] | None = None,
        space: dict[str, Any] | None = None,
    ) -> Scene:
        """`space` is a serialised `SceneSpace` (zones/adjacency/positions); participants not
        placed in it are put in its first zone."""
        participant_actor_ids = participant_actor_ids or []
        scene_state = dict(state or {})
        if space is not None:
            space = dict(space)
            positions = dict(space.get("positions", {}))
            first_zone = space["zones"][0]["key"]
            for actor_id in participant_actor_ids:
                positions.setdefault(
                    str(actor_id),
                    {"zone": first_zone, "engaged_with": [], "cover": "none", "elevated": False},
                )
            space["positions"] = positions
            scene_state["space"] = space
        async with self._tx(h) as tx:
            scene = Scene(
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                location_id=location_id,
                scene_type=scene_type,
                start_tick=tx.clock.current_tick,
                local_tick=tx.clock.current_tick,
                state=scene_state,
            )
            self.session.add(scene)
            await self.session.flush()
            entities = []
            for actor_id in participant_actor_ids:
                actor = await self._get(Actor, actor_id, what="actor")
                if location_id is not None and actor.current_location_id != location_id:
                    raise WorldError(f"actor {actor_id} is not at the scene location")
                if await self._active_participation(actor_id) is not None:
                    raise WorldError(f"actor {actor_id} is already in an active scene")
                entities.append((actor.entity_id, "participant"))
            event = await tx.emit(
                ev.SceneStarted(
                    scene_id=scene.id,
                    location_id=location_id,
                    scene_type=scene_type,
                    participant_actor_ids=participant_actor_ids,
                ),
                scene=scene,
                location_id=location_id,
                entities=entities,
            )
            scene.start_event_id = event.id
            for actor_id in participant_actor_ids:
                actor = await self._get(Actor, actor_id, what="actor")
                self.session.add(
                    SceneParticipant(scene_id=scene.id, actor_id=actor_id, joined_event_id=event.id)
                )
                actor.current_scene_id = scene.id
                actor.updated_event_id = event.id
        return scene

    async def end_scene(self, h: CampaignHandle, scene_id: uuid.UUID) -> Event:
        async with self._tx(h) as tx:
            scene = await self._get(Scene, scene_id, what="scene")
            if scene.status != "active":
                raise WorldError("scene is not active")
            event = await tx.emit(ev.SceneEnded(scene_id=scene.id), scene=scene)
            scene.status = "ended"
            scene.end_event_id = event.id
            scene.end_tick = tx.clock.current_tick
            participants = (
                (
                    await self.session.execute(
                        select(SceneParticipant).where(
                            SceneParticipant.scene_id == scene.id,
                            SceneParticipant.left_event_id.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for p in participants:
                p.left_event_id = event.id
                actor = await self._get(Actor, p.actor_id, what="actor")
                actor.current_scene_id = None
                actor.updated_event_id = event.id
        return event

    # -- time ----------------------------------------------------------------------------------

    async def advance_time(
        self,
        h: CampaignHandle,
        seconds: int,
        *,
        reason: str = "wait",
        scene_id: uuid.UUID | None = None,
    ) -> Event:
        async with self._tx(h) as tx:
            scene = await self.session.get(Scene, scene_id) if scene_id else None
            return await self._advance_clock(tx, seconds, reason=reason, scene=scene)

    async def _advance_clock(
        self,
        tx: EventTransaction,
        seconds: int,
        *,
        reason: str,
        cause: Event | None = None,
        scene: Scene | None = None,
    ) -> Event:
        scene_ = scene
        """`scene` is the scene whose play caused the advance (an action, a conversation,
        travel): it always follows the clock. Live scenes (a human participant) follow too;
        other scenes lag until a reunion fast-forwards them (time-accounting §3–§5)."""
        if seconds <= 0:
            raise WorldError("time only moves forward")
        from_tick = tx.clock.current_tick
        to_tick = from_tick + seconds
        event = await tx.emit(
            ev.TimeAdvanced(from_tick=from_tick, to_tick=to_tick, seconds=seconds, reason=reason),
            game_tick=to_tick,
            cause=cause,
        )
        tx.clock.current_tick = to_tick
        # Live scenes (a human-controlled participant) follow the clock; offscreen scenes keep
        # their local_tick behind and are fast-forwarded at reunion (time-accounting §3–§5;
        # the bounded catch-up call belongs to the orchestrator, deterministic systems to 08).
        for scene in (
            (
                await self.session.execute(
                    select(Scene).where(
                        Scene.timeline_id == tx.timeline_id, Scene.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        ):
            if scene.local_tick == from_tick and (
                (scene_ is not None and scene.id == scene_.id) or await self._has_human(scene.id)
            ):
                scene.local_tick = to_tick
                tx.touch_scene(scene)
        # scheduled events whose tick has come fire inside this transaction
        from app.services.schedule import ScheduleService

        await ScheduleService(self.session).fire_due(tx, to_tick)
        return event

    async def _has_human(self, scene_id: uuid.UUID) -> bool:
        rows = (
            await self.session.execute(
                select(ActorController.controller_type)
                .join(SceneParticipant, SceneParticipant.actor_id == ActorController.actor_id)
                .where(
                    SceneParticipant.scene_id == scene_id,
                    SceneParticipant.left_event_id.is_(None),
                    ActorController.valid_until_event_id.is_(None),
                )
            )
        ).scalars()
        return any(c == "human" for c in rows)

    # -- generic entities, materialization --------------------------------------------------------

    async def create_entity(
        self,
        h: CampaignHandle,
        entity_type: str,
        name: str,
        *,
        importance_tier: str = "standard",
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        """Entities that are neither actors, locations nor items (cultures, conflicts,
        pressures, opportunities): identity + metadata, nothing mechanical."""
        async with self._tx(h) as tx:
            entity = Entity(
                campaign_id=h.campaign_id,
                entity_type=entity_type,
                canonical_name=name,
                importance_tier=importance_tier,
                metadata_=metadata or {},
            )
            self.session.add(entity)
            await self.session.flush()
            event = await tx.emit(
                ev.EntityCreated(entity_id=entity.id, entity_type=entity_type, name=name),
                entities=[(entity.id, "subject")],
            )
            entity.created_event_id = event.id
        return entity

    async def materialize_location(
        self,
        h: CampaignHandle,
        location_id: uuid.UUID,
        *,
        space: dict[str, Any],
        features: list[dict[str, Any]],
        entry_zone: str | None = None,
    ) -> Location:
        """Give an outline/latent location a playable space (campaign-generation §27). Existing
        established features are kept; new ones are added as latent canon."""
        async with self._tx(h) as tx:
            loc = await self._get(Location, location_id, what="location")
            before = loc.detail_level
            if before == "materialized":
                raise WorldError("location is already materialized")
            props = dict(loc.properties or {})
            props["space"] = space
            props["features"] = list(props.get("features", [])) + list(features)
            if entry_zone:
                props["entry_zone"] = entry_zone
            event = await tx.emit(
                ev.LocationMaterialized(
                    location_id=loc.id, from_detail=before, zones=len(space.get("zones", []))
                ),
                location_id=loc.id,
                entities=[(loc.entity_id, "subject")],
            )
            loc.properties = props
            loc.detail_level = "materialized"
            ent = await self._get(Entity, loc.entity_id, what="entity")
            ent.metadata_ = {**(ent.metadata_ or {}), "materialized_event_id": str(event.id)}
        return loc

    async def add_faction_member(
        self, h: CampaignHandle, faction_id: uuid.UUID, actor_id: uuid.UUID, role: str | None = None
    ) -> FactionMembership:
        async with self._tx(h) as tx:
            actor = await self._get(Actor, actor_id, what="actor")
            await self._get(Faction, faction_id, what="faction")
            event = await tx.emit(
                ev.FactionMemberJoined(faction_id=faction_id, actor_id=actor_id, role=role),
                entities=[(actor.entity_id, "subject")],
            )
            row = FactionMembership(
                faction_id=faction_id, actor_id=actor_id, role=role, joined_event_id=event.id
            )
            self.session.add(row)
        return row

    # -- factions and parties ------------------------------------------------------------------

    async def create_faction(
        self,
        h: CampaignHandle,
        name: str,
        *,
        description: str | None = None,
        resources: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
        members: dict[uuid.UUID, str] | None = None,
        public: bool = False,
    ) -> Faction:
        """A faction and its memberships (database-schema §5). `public=False` means its
        existence is not general knowledge: nothing here creates beliefs for anyone."""
        async with self._tx(h) as tx:
            f = Faction(
                campaign_id=h.campaign_id,
                name=name,
                description=description,
                resources=resources or {},
                capabilities={**(capabilities or {}), "public": public},
            )
            self.session.add(f)
            await self.session.flush()
            event = await tx.emit(
                ev.FactionCreated(
                    faction_id=f.id, name=name, member_actor_ids=list((members or {}).keys())
                )
            )
            f.created_event_id = event.id
            for actor_id, role in (members or {}).items():
                await self._get(Actor, actor_id, what="actor")
                self.session.add(
                    FactionMembership(
                        faction_id=f.id, actor_id=actor_id, role=role, joined_event_id=event.id
                    )
                )
        return f

    async def create_party(
        self,
        h: CampaignHandle,
        name: str,
        member_actor_ids: list[uuid.UUID],
        *,
        shared_resources: dict[str, Any] | None = None,
    ) -> Party:
        async with self._tx(h) as tx:
            party = Party(
                campaign_id=h.campaign_id, name=name, shared_resources=shared_resources or {}
            )
            self.session.add(party)
            await self.session.flush()
            event = await tx.emit(
                ev.PartyCreated(party_id=party.id, name=name, member_actor_ids=member_actor_ids)
            )
            party.created_event_id = event.id
            for aid in member_actor_ids:
                await self._get(Actor, aid, what="actor")
                self.session.add(
                    PartyMembership(party_id=party.id, actor_id=aid, joined_event_id=event.id)
                )
        return party

    # -- reads ---------------------------------------------------------------------------------

    async def events(self, h: CampaignHandle) -> list[Event]:
        return list(
            (
                await self.session.execute(
                    select(Event)
                    .where(Event.timeline_id == h.timeline_id)
                    .order_by(Event.sequence_number)
                )
            )
            .scalars()
            .all()
        )

    async def clock(self, h: CampaignHandle) -> WorldClock:
        return await self._get(WorldClock, h.timeline_id, what="world clock")
