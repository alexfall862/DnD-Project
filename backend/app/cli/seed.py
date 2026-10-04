"""Offline seed command (`make seed-demo`): create a Frostbridge campaign directly in the
database — no running API needed — and print its symbolic map as JSON.

    uv run python -m app.cli.seed                 # full Frostbridge fixture
    uv run python -m app.cli.seed --fixture tavern  # the small Red Lantern scene
    uv run python -m app.cli.seed --name my-game --quiet
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.persistence.db import make_engine, make_session_factory


async def run(fixture: str, name: str | None, quiet: bool) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_session_factory(engine)() as session:
            if fixture == "tavern":
                from app.seeds.frostbridge_tavern import seed_tavern

                w = await seed_tavern(
                    session,
                    name=name or "frostbridge-tavern",
                    engine_version=settings.engine_version,
                )
            else:
                from app.seeds.frostbridge import seed_frostbridge

                w = await seed_frostbridge(
                    session, name=name or "frostbridge", engine_version=settings.engine_version
                )
            await session.commit()
            summary = w.summary()
    finally:
        await engine.dispose()
    if quiet:
        print(summary["campaign_id"])
    else:
        print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed a Frostbridge campaign into DATABASE_URL")
    ap.add_argument("--fixture", choices=("frostbridge", "tavern"), default="frostbridge")
    ap.add_argument("--name", default=None)
    ap.add_argument("--quiet", action="store_true", help="print only the campaign id")
    args = ap.parse_args(argv)
    return asyncio.run(run(args.fixture, args.name, args.quiet))


if __name__ == "__main__":
    sys.exit(main())
