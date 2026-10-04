# AI TTRPG Engine

A local-first, persistent AI-powered tabletop RPG engine. The application owns objective
truth, rules, randomness, state, events and memory; language models interpret, roleplay,
propose and narrate within permissions. The full design is in [`docs/`](docs/README.md);
[`docs/PROMPT.md`](docs/PROMPT.md) is the standing instruction for the coding agent and
[`docs/tasks/README.md`](docs/tasks/README.md) is the milestone order.

## Quickstart (Windows dev box)

Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/), GNU make (both via `winget`).

```bash
make setup      # backend/.venv + .env from .env.example
make db-up      # PostgreSQL 17 + pgvector in Docker
make migrate    # alembic upgrade head
make api        # http://localhost:8000/api/v1/health  (docs at /api/docs)
make test       # unit + integration (integration needs db-up)
```

Inference is optional for development: put your A9 token in `.env` as `A9_TOKEN` when you
want real-model runs (`make eval-local`, the 04b spike, the 06d play harness).

## Status

Milestone 00 (bootstrap). See `docs/tasks/` for what each milestone delivers and
`docs/DECISIONS.md` for locked decisions, including the implementation-start adjustments.
