# Milestone 04b — Model Capability Spike (throwaway)

Measures whether the configured A9 project can produce the structured outputs the architecture
assumes (`docs/specifications/ai-contracts.md`, `communication-and-knowledge.md` §2–3) at the
latencies `turn-budget-and-latency.md` assumes. **No database, no orchestrator, not product
code.** Output: numbers in `docs/HARDWARE-TARGET.md`, a report in `docs/spikes/`, and a
go/adjust decision in `docs/DECISIONS.md`.

```
uv --directory backend run python ../scripts/spike/run.py --n 50            # full run
uv --directory backend run python ../scripts/spike/run.py --n 3 --cases renn_lie   # smoke
uv --directory backend run python ../scripts/spike/run.py --n 50 --mode prompt_only
```

Cases (`cases.py`), each a hand-written least-privilege context package with an answer key:

| case | role | what it measures |
|---|---|---|
| `elara_whisper` | AI Player | `conveys[]` with `belief_ref`s inside Elara's perspective; private vs. spoken |
| `mira_evades` | NPC Actor | partial-fidelity reveal or evasion under fear; no leakage beyond Mira's facts |
| `renn_lie` | NPC Actor | `knowingly_false` + `conveys` with `deliberate_false` on a `fact_ref` |
| `narrator_tavern` | Narrator | second-person prose from rendered observations only; forbidden tokens absent |
| `intent_*` (5) | Intent Interpreter | decomposition, whisper channel, clarification, `asserted_facts`, time band |

Per case the runner reports: schema-valid rate (raw, and after one bounded repair call),
answer-key pass rate, `conveys` authorization violations (refs outside the speaker's supplied
context), latency p50/p95, tokens, and saves 10 raw samples for manual in-character judgement.

Raw JSONL lands in `scripts/spike/out/` (git-ignored). Every request opens with a unique
`run_id` line so A9 cannot share sessions between calls.
