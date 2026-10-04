# AI TTRPG Engine — standing instructions for the coding agent

This repository implements the persistent AI-powered tabletop RPG engine specified in `docs/`.
**`docs/PROMPT.md` is the authoritative standing instruction.** Read it and `docs/GLOSSARY.md`
once per session; then, for each milestone, read only the `## Read` context pack in its
`docs/tasks/milestone-*.md` file. Do not reread the whole bundle per ticket.

## Non-negotiables (summary; PROMPT.md has the full 18 invariants)

- LLMs propose; the engine commits. Every proposal is schema/reference/authorization/rules/
  version validated before any state change.
- Objective truth (`Fact`) and subjective knowledge (`Belief`, `Claim`, `Observation`, `Memory`)
  are separate. Perspective is an authorization boundary enforced in services/repositories,
  never a prompt convention. AI actor context goes through `PerspectiveService` only.
- Every authoritative projection mutation commits with an `Event` in the same transaction.
- All randomness comes from the engine's dice service. No `eval`/`exec` for rules.
- Narration follows resolution and is never parsed for state.
- Every turn is budgeted and measured (`turn_metrics`) from the first orchestrator commit.
- If a leak happens, fix the retrieval/authorization path first; prompts are defence in depth.
- Before changing a foundational boundary: name the conflicting sections, propose the smallest
  change, and record it in `docs/DECISIONS.md` *before* implementing.

## Where things are

| Path | Purpose |
|---|---|
| `docs/` | Planning bundle v0.2 (+ implementation-start decisions). `docs/DECISIONS.md` is the decision log. |
| `docs/tasks/` | One file per milestone; `docs/tasks/README.md` is the order. |
| `docs/HARDWARE-TARGET.md` | Inference host and measured profile numbers (filled by the 04b spike). |
| `backend/` | Python project: FastAPI app in `backend/app/`, Alembic in `backend/migrations/`, tests in `backend/tests/`. |
| `backend/rulesets/core_adventure/` | Declarative first ruleset (from Milestone 02a). |
| `scripts/` | Dev scripts; `scripts/spike/` is the throwaway 04b model spike. |
| `frontend/` | Placeholder until Milestone 10. |

## Environment facts

- Dev box: Windows 11, Git Bash + PowerShell. Use forward slashes and POSIX syntax in the Bash
  tool; `make` (ezwinports) and `uv` are installed via winget.
- PostgreSQL + pgvector runs in Docker Desktop via `docker-compose.yml` (`make db-up`).
  Integration tests use the real database `ttrpg_test` on the same server.
- Inference: the **A9 gateway on afhserver over Tailscale** (OpenAI-compatible). `model` is
  `ttrpg/local-general` = project `ttrpg` / GLM-4.5-Air; verify the response's `model` echoes it.
  409 = not loaded (wait Retry-After ≈ 2 min, never substitute); 503 = busy (5 s). 32k context.
  22.5 tok/s out; prefix caching works, so render stable context first. Token in `.env` as `A9_TOKEN`, never in source. A9 keeps per-session memory
  keyed on the opening message, prepends its own persona unless the project has none, and drops
  client tool definitions — the provider adapter defeats all three (`docs/DECISIONS.md`,
  "Added at implementation start"). Retry on 503 (+Retry-After) and 409.
- `FakeModelProvider` drives CI. Real-model behaviour lives in `make eval-local` only.

## Commands

`make db-up` · `make migrate` · `make api` · `make test` (+ `test-unit`, `test-integration`,
`test-invariants`, `test-leakage`, `test-rules`, `test-replay`) · `make reset-db` ·
`make seed-demo` · `make play` · `make eval-local`. See `Makefile`.

## Working style

- Work milestone by milestone; decompose each into tickets with Goal / Context / Likely files /
  Requirements / Invariants / Tests / Out of scope / Acceptance (`docs/architecture/05-implementation-plan.md` §26).
- Smallest coherent slice, then tests, then run them, then update the milestone file's status.
- Prefer clear modules, explicit Pydantic types, small services, DB constraints, pure functions,
  DI for providers. Module and type names should make "objective truth vs. one actor's
  perspective" obvious.
- Do not opportunistically implement later-milestone features or deferred scope.
- Event payloads: `payload_version` recorded, no upcasters before v0.1; `make reset-db` is the
  migration path for dev campaigns.
