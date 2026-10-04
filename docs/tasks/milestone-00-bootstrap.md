# Milestone 00 — Bootstrap

## Goal
Create a reproducible development environment and empty application shell.

## Read
`architecture/05-implementation-plan.md` §2–§4, §22; `PROMPT.md`; `GLOSSARY.md`.

## Context
Read the implementation plan and PROMPT.md. Do not implement game systems yet.

## Likely files
`docker-compose.yml`, `.env.example`, `Makefile`, backend app bootstrap, Alembic config, `CLAUDE.md`.

## Requirements
- FastAPI backend.
- ~~Next.js/React/TypeScript frontend.~~ Deferred to Milestone 10 (`DECISIONS.md`, implementation-start decisions). Only a `frontend/` placeholder README is created here.
- PostgreSQL.
- Alembic migrations.
- pytest.
- Docker Compose and documented native startup.
- `GET /api/v1/health`.
- Make targets: `dev`, `api`, `web`, `migrate`, `test`.

## Invariants
No game architecture belongs in frontend-only state. LLM credentials remain optional.

## Tests
Health endpoint, database connection, migration up/down smoke test.

## Out of scope
Game models, rules, AI calls.

## Acceptance
Fresh checkout starts successfully and `/api/v1/health` returns OK with database status.

## Status
**Done — 2026-10-03.** Notes from implementation:
- Database host port is **5434** (5432/5433 are taken by other local Docker projects).
- `uv` resolved Python 3.12.x for `backend/.venv`; `make`/`uv` installed via winget.
- Tests: `tests/unit/test_health_degraded.py` (health reports a missing DB instead of failing),
  `tests/integration/{test_database,test_health_db,test_migrations}.py` against `ttrpg_test`.
  Integration tests self-skip with a message when the database is down.
- Migration `0000_extensions` installs `pgcrypto` and `vector`; schema migrations start at
  `0001` per `specifications/database-schema.md` §23.
- Frontend scaffold deferred to Milestone 10 (`DECISIONS.md`).
