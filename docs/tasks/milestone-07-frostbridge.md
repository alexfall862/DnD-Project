# Milestone 07 — Frostbridge Demo

## Goal
Implement the deterministic Frostbridge vertical-slice fixture.

## Read
`specifications/frostbridge-demo.md` (all); `specifications/communication-and-knowledge.md` §8; `specifications/belief-update-rules.md` §4 worked values; `testing/vertical-slice.md`; `testing/knowledge-leakage.md` §2–§5, §12, §19.

## Implement
All content in `specifications/frostbridge-demo.md`: locations/topology, actors/controllers/party, facts/beliefs/relationships/goals/plans, locked mystery/clues, River Compact, quarry pressure, items/documents, scheduled events, opening scene, combat thieves.

## Required scenarios
Mira evasion; Renn deception; private whisper; companion disagreement; split-party investigation; dagger discovery; warehouse combat/improvisation; reunion knowledge exchange; time advance/evidence destruction.

## Invariants
Fixture truth is deterministic; mystery answer locked; hidden item property remains hidden; party knowledge remains per-actor.

## Tests
Script full deterministic path with FakeModelProvider and fixed RNG.

## Acceptance
Frostbridge integration test demonstrates every major v0.1 architecture concept except procedural campaign generation.
