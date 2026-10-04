# Milestone 10 — Player & Debug UI

## Goal
Make the vertical slice playable from the browser without direct API/database tooling.

## Read
`architecture/05-implementation-plan.md` §19–§20; `specifications/api-contracts.md` (all); `specifications/human-visibility.md` (all); `specifications/turn-budget-and-latency.md` §6–§7; `testing/testing-strategy.md` §20–§21; `testing/design-iteration.md` §5.

## Views
Play, Character, Party, Journal, Encyclopedia, World, Settings, Debug.

## Play UI
Narration feed, labeled NPC/AI-PC dialogue, visible rolls, mechanical notices, input channels Auto/Do/Say/Whisper/Private/OOC.

## Character/party UI
Attributes, skills, resources, abilities, conditions, equipment/inventory, visible companion status. Do not expose private relationship numbers/goals in normal mode.

## Debug UI
Events, objective facts, actor perspectives, comparison view, rolls, resolution traces, model runs, ContextSnapshots, memory, goals, clocks, mysteries, scheduled jobs.

## Invariants
Frontend never derives state by parsing narration. Normal APIs remain perspective-safe.

## Tests
Core browser flows and hidden-data absence.

## Acceptance
Complete Frostbridge scripted scenario is playable from UI, and a developer can expand a turn to trace its internal resolution.
