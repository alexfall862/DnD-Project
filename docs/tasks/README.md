# Milestone Index (v0.2)

Work in this order unless a documented dependency requires a small adjustment:

1. `milestone-00-bootstrap.md`
2. `milestone-01-world-events.md`
3. `milestone-02a-rules-core.md`
4. `milestone-02b-rules-actions-combat.md`
5. `milestone-03-perspective.md`
6. `milestone-04-memory.md`
7. `milestone-04b-model-capability-spike.md` — **gate**: fills `HARDWARE-TARGET.md`, records a go/adjust decision. Has no code dependencies, so it runs as a parallel track alongside 00–04 (`DECISIONS.md`); it must still be *decided* before 05 starts.
8. `milestone-05-ai-infrastructure.md`
9. `milestone-06a-intent-and-orchestrator.md`
10. `milestone-06b-ai-actors.md`
11. `milestone-06c-narration-and-governor.md`
12. `milestone-06d-cli-play-harness.md` — **first playable**; design-iteration loop starts here
13. `milestone-07-frostbridge.md`
14. `milestone-08-world-simulation.md`
15. `milestone-09-worldgen.md`
16. `milestone-10-player-ui.md`
17. `milestone-11-persistence-stress.md`
18. `milestone-12-branching.md`
19. `milestone-13-polish-v01.md`

Each milestone has a `## Read` section: the context pack for that milestone. Read `GLOSSARY.md`
and `PROMPT.md` once, then only the listed sections per ticket, rather than every document.

Each milestone should be decomposed into focused tickets using the template in
`architecture/05-implementation-plan.md` §26 and `PROMPT.md`.
