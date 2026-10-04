"""Encounters, pluggable initiative and the action economy (rules-engine §12, §16;
core-adventure §8).

`Encounter` tracks participants, initiative order, round and whose turn it is, and each
actor's per-turn budget (Core Adventure: 1 Major, 1 Movement, 1 Reaction). Initiative is a
provider: the default rolls the ruleset's `check.initiative` per actor, descending, with ties
broken by higher Awareness and then an engine-owned random choice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.core import RulesEngine
    from app.engine.stats import ActorState


class EncounterError(ValueError):
    pass


@dataclass
class TurnBudget:
    major: int = 1
    movement: int = 1
    reaction: int = 1
    free: int = 99

    def can_pay(self, cost: dict[str, int | bool]) -> bool:
        return all(
            getattr(self, k) >= 1
            for k, v in cost.items()
            if k in ("major", "movement", "reaction", "free") and v
        )

    def pay(self, cost: dict[str, int | bool]) -> None:
        for k, v in cost.items():
            if k in ("major", "movement", "reaction", "free") and v:
                setattr(self, k, getattr(self, k) - 1)

    def to_dict(self) -> dict[str, int]:
        return {"major": self.major, "movement": self.movement, "reaction": self.reaction}


@dataclass
class InitiativeEntry:
    actor: str
    total: int
    tiebreak: int
    roll_seed: int | None = None


InitiativeProvider = Callable[["RulesEngine", dict[str, "ActorState"]], list[InitiativeEntry]]


def default_initiative(engine: RulesEngine, states: dict[str, ActorState]) -> list[InitiativeEntry]:
    """Core Adventure: 1d20 + Agility descending; ties → higher Awareness, then engine random."""
    entries: list[InitiativeEntry] = []
    for key, st in states.items():
        r = engine.check(st, "check.initiative", purpose="initiative")
        entries.append(
            InitiativeEntry(key, r.total, engine.stat(st, "skill.awareness").value, r.roll.seed)
        )
    # resolve remaining ties with an engine-owned random pick, deterministic under the seed stream
    groups: dict[tuple[int, int], list[InitiativeEntry]] = {}
    for e in entries:
        groups.setdefault((e.total, e.tiebreak), []).append(e)
    ordered: list[InitiativeEntry] = []
    for key in sorted(groups, reverse=True):
        group = groups[key]
        while len(group) > 1:
            idx = engine.dice.choose(len(group), purpose="initiative tie-break")
            ordered.append(group.pop(idx))
        ordered.extend(group)
    return ordered


@dataclass
class Encounter:
    key: str
    participants: list[str]
    sides: dict[str, str]  # actor -> side name
    order: list[InitiativeEntry] = field(default_factory=list)
    round: int = 0
    turn_index: int = -1
    budgets: dict[str, TurnBudget] = field(default_factory=dict)
    status: str = "pending"  # pending | active | ended
    economy: dict[str, int] = field(
        default_factory=lambda: {"major": 1, "movement": 1, "reaction": 1}
    )
    departed: list[str] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)

    # -- lifecycle ---------------------------------------------------------------------------

    def start(
        self,
        engine: RulesEngine,
        states: dict[str, ActorState],
        provider: InitiativeProvider | None = None,
    ) -> list[InitiativeEntry]:
        if self.status != "pending":
            raise EncounterError("encounter already started")
        self.economy = dict(engine.ruleset.manifest.settings.get("action_economy", self.economy))
        provider = provider or default_initiative
        self.order = provider(engine, {k: states[k] for k in self.participants})
        self.budgets = {k: TurnBudget(**self.economy) for k in self.participants}
        self.status = "active"
        self.round = 1
        self.turn_index = 0
        self.log.append({"round": 1, "event": "start", "order": [e.actor for e in self.order]})
        return self.order

    @property
    def current_actor(self) -> str | None:
        if self.status != "active" or not self.order:
            return None
        return self.order[self.turn_index].actor

    def budget(self, actor: str) -> TurnBudget:
        return self.budgets[actor]

    def active_order(self) -> list[InitiativeEntry]:
        return [e for e in self.order if e.actor not in self.departed]

    def advance_turn(self) -> tuple[str | None, bool]:
        """Move to the next living/present actor. Returns (actor, new_round_started)."""
        if self.status != "active":
            raise EncounterError("encounter not active")
        n = len(self.order)
        for _ in range(n):
            self.turn_index += 1
            new_round = False
            if self.turn_index >= n:
                self.turn_index = 0
                self.round += 1
                new_round = True
            actor = self.order[self.turn_index].actor
            if actor in self.departed:
                continue
            self.budgets[actor] = TurnBudget(**self.economy)
            return actor, new_round
        return None, False

    def remove(self, actor: str, reason: str) -> None:
        if actor not in self.departed:
            self.departed.append(actor)
            self.log.append(
                {"round": self.round, "event": "departed", "actor": actor, "reason": reason}
            )

    def hostile(self, a: str, b: str) -> bool:
        if a not in self.sides or b not in self.sides:
            return False  # a bystander is nobody's enemy
        return self.sides[a] != self.sides[b]

    def living_sides(self, states: dict[str, ActorState]) -> set[str]:
        out = set()
        for a in self.participants:
            if a in self.departed:
                continue
            st = states.get(a)
            if (
                st is None
                or st.has_condition("condition.incapacitated")
                or st.has_condition("condition.surrendered")
            ):
                continue
            if a in self.sides:  # bystanders have no side and do not keep a fight alive
                out.add(self.sides[a])
        return out

    def maybe_end(self, states: dict[str, ActorState]) -> bool:
        if self.status == "active" and len(self.living_sides(states)) <= 1:
            self.status = "ended"
            self.log.append(
                {"round": self.round, "event": "end", "standing": sorted(self.living_sides(states))}
            )
            return True
        return False

    # -- (de)serialisation -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "participants": self.participants,
            "sides": self.sides,
            "order": [e.__dict__ for e in self.order],
            "round": self.round,
            "turn_index": self.turn_index,
            "budgets": {k: b.to_dict() for k, b in self.budgets.items()},
            "status": self.status,
            "economy": self.economy,
            "departed": self.departed,
            "log": self.log,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Encounter:
        enc = cls(d["key"], list(d["participants"]), dict(d["sides"]))
        enc.order = [InitiativeEntry(**e) for e in d.get("order", [])]
        enc.round = d.get("round", 0)
        enc.turn_index = d.get("turn_index", -1)
        enc.budgets = {k: TurnBudget(**b) for k, b in d.get("budgets", {}).items()}
        enc.status = d.get("status", "pending")
        enc.economy = dict(d.get("economy", enc.economy))
        enc.departed = list(d.get("departed", []))
        enc.log = list(d.get("log", []))
        return enc
