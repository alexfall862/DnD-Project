"""Buying and selling (DECISIONS 10d, Phase 3; play session 2: "we bought a whole wagon" with
no coin spent).

Prices come from the ruleset's goods list, adjusted by the seller's recorded price for the
party (`set_price`, the outcome of haggling or goodwill). A purchase moves coin from buyer to
seller and puts the goods in the buyer's hands; one the buyer cannot afford does not happen.
Selling fetches half the list price, if the buyer has the coin. Every change goes through the
consequence service (coin as effects, items through the world service), with its events.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.core import RulesEngine
from app.engine.ruleset import GoodsDef
from app.persistence.models import Actor, Entity, Item, Situation
from app.services.consequences import ConsequenceContext, ConsequenceError, ConsequenceService
from app.services.world import WorldService

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "dozen": 12,
    "couple": 2,
}
MAX_QTY = 20
STOP = {"of", "the", "and", "for", "with", "some", "sack", "bolt", "flask", "mug", "night"}


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 3 and t.endswith("s") else t


@dataclass
class Quote:
    goods: GoodsDef
    qty: int
    unit_price: int
    total: int
    modifier_pct: int


class TradeService:
    def __init__(
        self, session: AsyncSession, engine: RulesEngine, consequences: ConsequenceService
    ) -> None:
        self.session = session
        self.engine = engine
        self.consequences = consequences
        self.world = WorldService(session)

    # -- what and how much ---------------------------------------------------------------------

    def find_goods(self, text: str) -> list[tuple[GoodsDef, int]]:
        """The listed goods the words name, each with a quantity ("two torches", "3 rations")."""
        words = _tokens(text)
        stems = [_stem(w) for w in words]
        found: list[tuple[GoodsDef, int]] = []
        for g in self.engine.ruleset.goods.values():
            name = [_stem(t) for t in _tokens(g.name) if t not in STOP] or [
                _stem(g.key.split(".", 1)[1])
            ]
            key_word = _stem(g.key.split(".", 1)[1].split("_")[-1])
            idx = None
            for i in range(len(stems)):
                if stems[i : i + len(name)] == name:
                    idx = i
                    break
            if idx is None and key_word in stems and len(key_word) > 3:
                idx = stems.index(key_word)
            if idx is None:
                continue
            qty = 1
            if idx > 0:
                prev = words[idx - 1]
                if prev.isdigit():
                    qty = int(prev)
                elif prev in NUMBER_WORDS:
                    qty = NUMBER_WORDS[prev]
            found.append((g, max(1, min(MAX_QTY, qty))))
        # the longest names win when one is inside another ("oil lantern" over "lamp oil")
        return found

    async def price_modifier(self, seller_id: uuid.UUID, buyer_id: uuid.UUID) -> int:
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == seller_id,
                        Situation.kind == "price",
                        Situation.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in rows:
            if not s.data.get("for") or str(buyer_id) in s.data["for"]:
                return int(s.data.get("percent", 0))
        return 0

    async def quote(
        self, goods: GoodsDef, qty: int, seller_id: uuid.UUID, buyer_id: uuid.UUID, *, selling=False
    ) -> Quote:
        pct = await self.price_modifier(seller_id, buyer_id)
        base = goods.price / 2 if selling else goods.price
        unit = max(
            1 if goods.price else 0, math.ceil(base * (100 + (-pct if selling else pct)) / 100)
        )
        return Quote(goods, qty, unit, unit * qty, pct)

    async def coin(self, c: ConsequenceContext, actor_id: uuid.UUID) -> int:
        loaded = await self.consequences.actions.load_scene(c.h, c.scene.id)
        st = loaded.ctx.states.get(str(actor_id))
        res = st.resources.get("resource.coin") if st else None
        return res.current if res else 0

    # -- buying and selling --------------------------------------------------------------------

    async def buy(
        self, c: ConsequenceContext, seller_id: uuid.UUID, text: str
    ) -> tuple[list[str], str | None]:
        """(what happened, why nothing did). All goods named are bought together or not at
        all."""
        wanted = self.find_goods(text)
        if not wanted:
            return [], "nothing you named is for sale here at a price you know"
        quotes = [await self.quote(g, q, seller_id, c.actor_id) for g, q in wanted]
        total = sum(q.total for q in quotes)
        have = await self.coin(c, c.actor_id)
        what = ", ".join(_label(q) for q in quotes)
        if total > have:
            return [], f"you can't afford {what}: it costs {total} coin and you have {have}"
        try:
            await self.consequences.pay(c, c.actor_id, seller_id, total)
        except ConsequenceError as exc:
            return [], str(exc)
        for q in quotes:
            if "service" in q.goods.tags or "food" in q.goods.tags and q.goods.item is None:
                continue  # a meal, a room, a bath: had, not carried
            name = q.goods.name if q.qty == 1 else f"{q.goods.name} ×{q.qty}"
            await self.world.create_item(
                c.h,
                name,
                template_key=q.goods.item,
                possessor_actor_id=c.actor_id,
                equipped=False,
                public_properties={"bought_for": q.total, "quantity": q.qty},
                provenance={"bought_from": str(seller_id)},
            )
        pct = quotes[0].modifier_pct
        note = f"You buy {what} for {total} coin" + (
            f" ({abs(pct)}% {'off' if pct < 0 else 'over list'})" if pct else ""
        )
        return [note + "."], None

    async def sell(
        self, c: ConsequenceContext, buyer_id: uuid.UUID, text: str
    ) -> tuple[list[str], str | None]:
        """Sell the first carried item the words name that the goods list prices."""
        me = await self.session.get(Actor, c.actor_id)
        rows = (
            await self.session.execute(
                select(Item, Entity)
                .join(Entity, Entity.id == Item.entity_id)
                .where(
                    Item.possessor_entity_id == me.entity_id,  # type: ignore[union-attr]
                    Item.destroyed_event_id.is_(None),
                )
            )
        ).all()
        words = {_stem(t) for t in _tokens(text)}
        for item, ent in rows:
            name = ent.canonical_name or item.template_key or ""
            if not ({_stem(t) for t in _tokens(name)} - set(STOP)) & words:
                continue
            goods = next(
                (
                    g
                    for g in self.engine.ruleset.goods.values()
                    if (item.template_key and g.item == item.template_key)
                    or _stem(g.name.lower()) == _stem(name.lower().split(" ×")[0])
                ),
                None,
            )
            if goods is None:
                return [], f"nobody here knows what to pay for {name}"
            q = await self.quote(goods, 1, buyer_id, c.actor_id, selling=True)
            if await self.coin(c, buyer_id) < q.total:
                return [], f"they can't pay {q.total} coin for {name}"
            ref = next((x.ref for x in c.cands if x.id == str(item.id)), name)
            gave = await self.consequences.apply_one(
                c, "give_item", {"from": "you", "item": ref, "to": str(buyer_id)}
            )
            if not gave.ok:
                return [], gave.reason
            await self.consequences.pay(c, buyer_id, c.actor_id, q.total)
            return [f"You sell {name} for {q.total} coin."], None
        return [], "you carry nothing like that to sell"


def _label(q: Quote) -> str:
    return q.goods.name.lower() if q.qty == 1 else f"{q.qty} × {q.goods.name.lower()}"
