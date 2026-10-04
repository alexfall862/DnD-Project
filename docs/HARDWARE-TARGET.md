# Hardware & Model Target (living file)

Fill this in before Milestone 04b and keep it current. `specifications/turn-budget-and-latency.md` §2 explains
why the abstract routing profiles need a concrete floor; the Milestone 04b spike produces the
measured numbers.

```yaml
updated: 2026-10-03 (04b spike measured; see docs/spikes/model-capability-2026-10-03.md)
inference_host:
  name: afhserver (separate Linux box on the tailnet; dev box is a Windows 11 workstation)
  gpu: ___                     # ask A9's owner; not reachable by SSH from the dev box
  vram_gb: ___
  system_ram_gb: ___
  cpu: ___
  serving_stack: A9 gateway    # OpenAI-compatible; `model` selects an A9 *project*, A9 picks the real model
  endpoint: http://afhserver.tail590cb0.ts.net:8100/v1   # or http://100.111.251.66:8100/v1
  auth: Bearer $A9_TOKEN + header X-A9-Client            # token lives in .env, never in source
  co_resident_models: 2        # A9 reports "two model slots"; 503+Retry-After when both busy, 409 during Deep-mode swap
  structured_output_support: ___  # unknown: A9 drops client tool definitions; response_format passthrough measured by the spike
  provider_memory: must be defeated  # A9 keys sessions on the opening message; no-persona/no-tools project + unique model_run_id first line
profiles:                      # `model` = A9 project; A9 currently routes all of them to `local-coder`
  fast_structured:    { model: ttrpg/local-general, quant: "?", ctx_window: 32768, measured_tps: 22.5, schema_valid_rate: 1.00 }   # GLM-4.5-Air; intent cases n=150
  balanced_reasoning: { model: ttrpg/local-general, quant: "?", ctx_window: 32768, measured_tps: 22.5, schema_valid_rate: 0.80 }   # AI Player / NPC Actor n=90 raw; 0.94 after one repair
  creative_narrative: { model: ttrpg/local-general, quant: "?", ctx_window: 32768, measured_tps: 22.5, schema_valid_rate: 1.00 }   # narrator p50 13.6 s total
  deep_world_author:  { model: ttrpg, quant: "?", ctx_window: "?", measured_tps: 43, schema_valid_rate: "not measured" }
  embedding:          { model: ___, dims: ___, measured_embeds_per_s: ___ }   # A9 exposes no embedding endpoint yet — see DECISIONS.md
cloud_fallback:
  enabled: false
  profiles_allowed: []         # e.g. [deep_world_author]
notes: |
  Model-swap cost (seconds): not measured (local-general was swapped out for the whole spike)
  Observed batching behaviour for concurrent requests: indicative only (n=2): two concurrent
    actor calls completed in ~15 s each vs ~12 s alone, i.e. ~1.6x throughput — llama.cpp
    appears to batch. Measure properly before relying on it.
  Latency model: ≈ 0.023 s per completion token + ~0.4 s per 1k prompt tokens. Completion
    length is the lever: a 520-token actor output costs ~12 s; 220 tokens would cost ~5 s.
```

Planning assumptions until measured (also stated in `specifications/turn-budget-and-latency.md`): one GPU,
one resident model per profile family, concurrent calls to the same model serialize or batch,
swaps are avoided within a turn.

## Probe 2026-10-03 (pre-spike, `ttrpg` project)

| Check | Result |
|---|---|
| `/v1/models` | `ttrpg` (a9-project), `local-coder`, `local-general` (a9-llamacpp slots) |
| `ttrpg` routes to | `local-coder` (the resident model; `local-general` returned 409 "swapped out, deep mode") |
| A9 prompt overhead | ~200–220 prompt tokens prepended even with persona `none` |
| `response_format: json_schema` | **not honored** (plain text came back) |
| `response_format: json_object` | **works** → structured output = json_object + prompt-described schema + engine validation |
| Session keying | identical opening messages share `a9.session_id`; a unique first line isolates. Adapter must prefix every request with `model_run_id`. |
| Throughput | ~48 completion tok/s (214 tokens in 4.4 s incl. prompt processing) |
| Streaming | SSE works; first chunk ≈ 0.12 s |
| Latency floor | ≈ 0.3–0.4 s for a 2-token reply |

Open: which model is `local-coder` / `local-general` (name, size, quant, ctx)? A coder model may
be a poor fit for narration and roleplay; the 04b spike will show it. Confirm with A9's owner.

## Probe 2026-10-03 (second, after A9 update): `ttrpg/local-general` = **GLM-4.5-Air**

A9 now keeps only GLM-4.5-Air loaded; `local-coder` is retired and the first probe/spike
numbers above describe a model that no longer exists. Request `model: "ttrpg/local-general"`;
A9 echoes it back (verify on every response) or answers 409 (not loaded; Retry-After ≈ 2 min —
never substitute). Context limit 32k tokens per request including the reply. Thinking mode off.

| Check | Result |
|---|---|
| Output rate | **22.5 completion tok/s** (185 tokens in 8.2 s) |
| Prompt reading, cold | ≈ 350 tok/s (2,250 tokens → TTFT 6.4 s); A9 states ~280 tok/s |
| **Prefix cache** | **works**: same system prompt again → TTFT 0.31 s, `cached_tokens` ≈ all. Stable content first in every prompt. |
| Two concurrent calls | serialized (6.4 s and 12.3 s); plan for wall time = sum |
| `json_object` | works but GLM wraps the object in a ```json fence; parse leniently |
| A9 prompt overhead | ~240 tokens prepended |
| Latency model | ≈ (uncached prompt tokens / 350) + (completion tokens / 22.5) s |

Implication for `turn-budget-and-latency.md` §3: with cached role prefixes, a 260-token actor
reply costs ≈ 11–12 s. Intent (~150 tokens, ~7 s) + two visible reactions (~23 s) + narrator
TTFT puts a complex social turn at ≈ 30 s to first narration token — the hard cap, double the
target. One visible reaction (degradation step 3) gives ≈ 19 s. See DECISIONS.md.
