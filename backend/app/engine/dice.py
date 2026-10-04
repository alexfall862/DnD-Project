"""Dice notation and seeded rolling (rules-engine §8). All randomness comes from here.

Notation: `NdM`, `dM` (N=1), optional keep-highest/lowest `khK`/`klK`, optional `+C`/`-C`
modifier, e.g. `1d20`, `2d6+3`, `4d6kh3`, `2d20kh1`, `d100`, `1d8-1`.

Every roll records expression, seed, raw dice, kept dice, modifier and total, so a
`RollRecord` can be replayed bit-for-bit with `roll(expression, seed=record.seed)`.
Seeds are drawn from a `SeedStream` (a seeded master generator) so an entire scripted
scenario is reproducible from one master seed.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

DICE_RE = re.compile(
    r"^\s*(?P<n>\d*)d(?P<m>\d+)(?:(?P<keep>k[hl])(?P<k>\d+))?\s*(?:(?P<sign>[+-])\s*(?P<mod>\d+))?\s*$",
    re.IGNORECASE,
)

MAX_DICE = 100
MAX_SIDES = 1000


class DiceError(ValueError):
    pass


@dataclass(frozen=True)
class DiceExpression:
    count: int
    sides: int
    keep: str | None = None  # "kh" | "kl"
    keep_n: int | None = None
    modifier: int = 0

    @property
    def text(self) -> str:
        s = f"{self.count}d{self.sides}"
        if self.keep:
            s += f"{self.keep}{self.keep_n}"
        if self.modifier:
            s += f"{self.modifier:+d}"
        return s

    @property
    def min_total(self) -> int:
        kept = self.keep_n if self.keep_n is not None else self.count
        return kept + self.modifier

    @property
    def max_total(self) -> int:
        kept = self.keep_n if self.keep_n is not None else self.count
        return kept * self.sides + self.modifier


def parse_dice(expression: str) -> DiceExpression:
    m = DICE_RE.match(expression)
    if not m:
        raise DiceError(f"invalid dice expression {expression!r}")
    count = int(m.group("n") or 1)
    sides = int(m.group("m"))
    if not 1 <= count <= MAX_DICE:
        raise DiceError(f"dice count must be 1..{MAX_DICE}")
    if not 2 <= sides <= MAX_SIDES:
        raise DiceError(f"sides must be 2..{MAX_SIDES}")
    keep = m.group("keep").lower() if m.group("keep") else None
    keep_n = int(m.group("k")) if m.group("k") else None
    if keep and (keep_n is None or not 1 <= keep_n <= count):
        raise DiceError("keep count must be 1..count")
    modifier = int(m.group("mod") or 0)
    if m.group("sign") == "-":
        modifier = -modifier
    return DiceExpression(count, sides, keep, keep_n, modifier)


@dataclass(frozen=True)
class RollRecord:
    expression: str
    seed: int
    raw: tuple[int, ...]
    kept: tuple[int, ...]
    modifier: int
    total: int
    purpose: str = ""
    visibility: str = "public"  # public | actor_only | hidden | debug
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def natural(self) -> int:
        """Highest kept die — what a 'natural 20 / natural 1' rule looks at for single dice."""
        return max(self.kept)


def roll_with_seed(expr: DiceExpression, seed: int) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    rng = random.Random(seed)
    raw = tuple(rng.randint(1, expr.sides) for _ in range(expr.count))
    if expr.keep == "kh":
        kept = tuple(sorted(raw, reverse=True)[: expr.keep_n])
    elif expr.keep == "kl":
        kept = tuple(sorted(raw)[: expr.keep_n])
    else:
        kept = raw
    return raw, kept, sum(kept) + expr.modifier


class SeedStream:
    """Deterministic source of per-roll seeds. One master seed reproduces a whole scenario."""

    def __init__(self, master_seed: int | None = None) -> None:
        if master_seed is None:
            master_seed = random.SystemRandom().getrandbits(63)
        self.master_seed = master_seed
        self._rng = random.Random(master_seed)
        self.count = 0

    def next_seed(self) -> int:
        self.count += 1
        return self._rng.getrandbits(63)


class DiceService:
    def __init__(self, seeds: SeedStream | None = None) -> None:
        self.seeds = seeds or SeedStream()
        self.history: list[RollRecord] = []

    def roll(
        self,
        expression: str,
        *,
        seed: int | None = None,
        purpose: str = "",
        visibility: str = "public",
        **extra: object,
    ) -> RollRecord:
        expr = parse_dice(expression)
        if seed is None:
            seed = self.seeds.next_seed()
        raw, kept, total = roll_with_seed(expr, seed)
        record = RollRecord(
            expression=expr.text,
            seed=seed,
            raw=raw,
            kept=kept,
            modifier=expr.modifier,
            total=total,
            purpose=purpose,
            visibility=visibility,
            extra=dict(extra),
        )
        self.history.append(record)
        return record

    def replay(self, record: RollRecord) -> RollRecord:
        """Re-roll a recorded roll; must produce identical dice."""
        return self.roll(
            record.expression,
            seed=record.seed,
            purpose=record.purpose,
            visibility=record.visibility,
            **record.extra,
        )

    def choose(self, options: int, *, purpose: str = "", seed: int | None = None) -> int:
        """Engine-owned random table / tie-break selection: index in [0, options)."""
        if options < 1:
            raise DiceError("choose needs at least one option")
        if seed is None:
            seed = self.seeds.next_seed()
        idx = random.Random(seed).randrange(options)
        self.history.append(
            RollRecord(f"choose({options})", seed, (idx,), (idx,), 0, idx, purpose, "hidden")
        )
        return idx
