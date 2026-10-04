"""Spike runner: calls A9 N times per case, validates, scores against answer keys, reports.

Usage (from repo root):
  uv --directory backend run python ../scripts/spike/run.py --n 50
  uv --directory backend run python ../scripts/spike/run.py --n 3 --cases renn_lie,intent_whisper
Options: --mode json_object|prompt_only  --model <a9 project>  --concurrency 2  --no-repair
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

sys.path.insert(0, str(Path(__file__).parent))
from cases import ALL_CASES, Case  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "out"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    p = REPO / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.split("#", 1)[0].strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("A9_")})
    return env


# ---------------------------------------------------------------------------------------------
# JSON extraction + validation
# ---------------------------------------------------------------------------------------------

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Lenient parse: direct, fenced, or first {...} block."""
    candidates = [text.strip()]
    m = FENCE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    last_err = None
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj, None
            last_err = "top-level JSON is not an object"
        except json.JSONDecodeError as e:
            last_err = str(e)
    return None, last_err


def validate(case: Case, obj: dict[str, Any]) -> list[str]:
    v = Draft202012Validator(case.schema)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in v.iter_errors(obj)][:8]


# ---------------------------------------------------------------------------------------------
# Answer-key scoring
# ---------------------------------------------------------------------------------------------

PHATIC_WORDS = 12


def _refs(obj: dict[str, Any]) -> list[str]:
    return [c.get("ref_id") for c in obj.get("conveys", []) if c.get("kind") in ("belief_ref", "fact_ref") and c.get("ref_id")]


def _prop_text(obj: dict[str, Any]) -> str:
    parts = []
    for c in obj.get("conveys", []):
        p = c.get("proposition") or {}
        if isinstance(p, dict):
            parts.append(" ".join(str(p.get(k) or "") for k in ("subject_entity_id", "predicate", "object_entity_id", "value")))
    return " ".join(parts).lower()


def score(case: Case, obj: dict[str, Any]) -> tuple[bool, list[str], int]:
    """Returns (key_pass, failures, authz_violations)."""
    fails: list[str] = []
    k = case.key
    refs = _refs(obj)
    authz = sum(1 for r in refs if r not in case.allowed_refs)
    if authz:
        fails.append(f"authz: refs outside perspective {[r for r in refs if r not in case.allowed_refs]}")
    # kind must match the id family (b_* = belief_ref, f_* = fact_ref)
    for c in obj.get("conveys", []):
        rid = c.get("ref_id") or ""
        if c.get("kind") == "belief_ref" and rid.startswith("f_") or c.get("kind") == "fact_ref" and rid.startswith("b_"):
            fails.append(f"ref kind mismatch: {c.get('kind')} {rid}")

    spoken = (obj.get("spoken_text") or "").strip()
    conveys = obj.get("conveys", [])
    if k.get("speech_requires_conveys") and spoken and len(spoken.split()) > PHATIC_WORDS and not conveys:
        fails.append("non-trivial speech with empty conveys")

    if "expect_any_ref" in k:
        hit = bool(set(refs) & k["expect_any_ref"])
        if not hit and k.get("or_proposition_mentions"):
            hit = any(w in _prop_text(obj) for w in k["or_proposition_mentions"])
        if not hit:
            fails.append("no expected ref/proposition in conveys")

    for word, allowed in k.get("mention_implies_ref", {}).items():
        if word in spoken.lower() and not (set(refs) & allowed) and not conveys:
            fails.append(f"speech mentions {word!r} but conveys is empty")

    if k.get("speech_act_consistent"):
        sa = obj.get("speech_act") or {}
        lying = sa.get("type") == "lie" or sa.get("knowingly_false") is True
        flagged = any(c.get("deliberate_false") for c in conveys)
        if lying != flagged:
            fails.append(f"speech_act lie={lying} but conveys deliberate_false={flagged}")

    if k.get("expect_deliberate_false") and not any(c.get("deliberate_false") for c in conveys):
        fails.append("expected a deliberate_false conveys item (the lie)")

    for r in k.get("must_not_assert_true", set()):
        for c in conveys:
            if c.get("ref_id") == r and c.get("stance") == "asserts_true" and not c.get("deliberate_false"):
                fails.append(f"confessed {r} as true")

    if "word_range" in k:
        n = len((obj.get("narration") or "").split())
        lo, hi = k["word_range"]
        if not lo <= n <= hi:
            fails.append(f"narration {n} words outside {lo}-{hi}")

    # intent keys
    if "channel" in k and obj.get("channel") != k["channel"]:
        fails.append(f"channel {obj.get('channel')} != {k['channel']}")
    if "requires_clarification" in k and obj.get("requires_clarification") != k["requires_clarification"]:
        fails.append(f"requires_clarification != {k['requires_clarification']}")
    if "min_intents" in k and len(obj.get("intents", [])) < k["min_intents"]:
        fails.append(f"fewer than {k['min_intents']} intents")
    if "targets_include" in k:
        seen = set(obj.get("targets", [])) | {i.get("target_ref") for i in obj.get("intents", [])}
        missing = k["targets_include"] - seen
        if missing:
            fails.append(f"targets missing {sorted(missing)}")
    if "conveys_min" in k and len(conveys) < k["conveys_min"]:
        fails.append("conveys too short")
    if "conveys_stance_any" in k and conveys and not ({c.get("stance") for c in conveys} & k["conveys_stance_any"]):
        fails.append("no conveys item with expected stance")
    if (
        "proposition_mentions" in k
        and conveys
        and not any(w in _prop_text(obj) for w in k["proposition_mentions"])
        and not (set(refs) & k.get("or_any_ref", set()))
    ):
        fails.append("proposition does not mention expected entity")
    if "time_band_not" in k and obj.get("conversation_time_band") in k["time_band_not"]:
        fails.append("time band should not be none for speech")
    if "asserted_min" in k and len(obj.get("asserted_facts", [])) < k["asserted_min"]:
        fails.append("no asserted_facts")
    if "asserted_class_any" in k and obj.get("asserted_facts") and not ({a.get("class") for a in obj["asserted_facts"]} & k["asserted_class_any"]):
        fails.append("asserted class unexpected")

    # forbidden tokens anywhere in free text
    blob = json.dumps(obj).lower()
    for tok in case.forbidden_tokens:
        if tok in blob:
            fails.append(f"forbidden token {tok!r} present")
    return (not fails, fails, authz)


# ---------------------------------------------------------------------------------------------
# A9 client
# ---------------------------------------------------------------------------------------------


class A9:
    def __init__(self, env: dict[str, str], model: str, mode: str, concurrency: int) -> None:
        self.client = httpx.AsyncClient(
            base_url=env["A9_BASE_URL"],
            headers={"Authorization": f"Bearer {env['A9_TOKEN']}", "X-A9-Client": env.get("A9_CLIENT_NAME", "ai-ttrpg-spike")},
            timeout=240,
        )
        self.model = model
        self.mode = mode
        self.sem = asyncio.Semaphore(concurrency)

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if self.mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        async with self.sem:
            for attempt in range(8):
                t0 = time.perf_counter()
                r = await self.client.post("/chat/completions", json=body)
                dt = time.perf_counter() - t0
                if r.status_code in (503, 409):
                    await asyncio.sleep(float(r.headers.get("Retry-After", "3")))
                    continue
                r.raise_for_status()
                j = r.json()
                if j.get("model") != self.model:
                    print(f"   WARNING: requested {self.model} but response model is {j.get('model')}", flush=True)
                return {"text": j["choices"][0]["message"]["content"], "latency": dt, "usage": j.get("usage", {}), "model": j.get("model"),
                        "cached_tokens": (j.get("usage", {}).get("prompt_tokens_details") or {}).get("cached_tokens")}
            raise RuntimeError("A9 busy after retries")

    async def ttft(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> float | None:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True}
        if self.mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        async with self.sem:
            t0 = time.perf_counter()
            async with self.client.stream("POST", "/chat/completions", json=body) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data:") and "[DONE]" not in line:
                        return time.perf_counter() - t0
        return None


# ---------------------------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------------------------


def messages_for(case: Case) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": case.system},
        {"role": "user", "content": f"run_id: {uuid.uuid4()}\n\n{case.user}"},
    ]


async def one_sample(a9: A9, case: Case, repair: bool) -> dict[str, Any]:
    msgs = messages_for(case)
    first = await a9.chat(msgs, max_tokens=case.max_tokens, temperature=case.temperature)
    obj, perr = extract_json(first["text"])
    errors = validate(case, obj) if obj else [f"json: {perr}"]
    rec: dict[str, Any] = {
        "case": case.name, "latency": first["latency"], "usage": first["usage"], "model": first["model"],
        "cached_tokens": first.get("cached_tokens"),
        "raw": first["text"], "valid_raw": not errors, "errors_raw": errors, "repaired": False,
        "valid_final": not errors, "key_pass": False, "key_fails": [], "authz_violations": 0,
    }
    if errors and repair:
        msgs2 = msgs + [
            {"role": "assistant", "content": first["text"]},
            {"role": "user", "content": "Your JSON failed validation:\n- " + "\n- ".join(errors) + "\nReturn the corrected JSON object only."},
        ]
        second = await a9.chat(msgs2, max_tokens=case.max_tokens, temperature=0.1)
        rec["repaired"] = True
        rec["latency_repair"] = second["latency"]
        obj, perr = extract_json(second["text"])
        errors = validate(case, obj) if obj else [f"json: {perr}"]
        rec["raw_repaired"] = second["text"]
        rec["valid_final"] = not errors
        rec["errors_final"] = errors
    if obj is not None and not errors:
        ok, fails, authz = score(case, obj)
        rec.update(key_pass=ok, key_fails=fails, authz_violations=authz, parsed=obj)
    return rec


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))
    return xs[i]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--cases", default="")
    ap.add_argument("--mode", choices=["json_object", "prompt_only"], default="json_object")
    ap.add_argument("--model", default=None)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    env = load_env()
    if not env.get("A9_TOKEN"):
        sys.exit("A9_TOKEN missing (.env)")
    model = args.model or env.get("MODEL_PROFILE_BALANCED_REASONING", "ttrpg")
    a9 = A9(env, model, args.mode, args.concurrency)
    wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
    cases = [c for c in ALL_CASES if not wanted or c.name in wanted]

    OUT.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    raw_path = OUT / f"{stamp}_{model.replace('/', '-')}_{args.mode}.jsonl"
    summary: list[dict[str, Any]] = []
    with raw_path.open("a", encoding="utf-8") as raw:
        for case in cases:
            print(f"== {case.name} ({case.role}) x {args.n} ==", flush=True)
            recs = await asyncio.gather(*(one_sample(a9, case, not args.no_repair) for _ in range(args.n)))
            for r in recs:
                raw.write(json.dumps(r, ensure_ascii=False) + "\n")
            ttft = None
            if case.role == "narrator":
                ttft = await a9.ttft(messages_for(case), max_tokens=case.max_tokens, temperature=case.temperature)
            lat = [r["latency"] for r in recs]
            row = {
                "case": case.name, "role": case.role, "n": len(recs),
                "valid_raw": sum(r["valid_raw"] for r in recs) / len(recs),
                "valid_final": sum(r["valid_final"] for r in recs) / len(recs),
                "key_pass": sum(r["key_pass"] for r in recs) / len(recs),
                "authz_violations": sum(r["authz_violations"] for r in recs),
                "p50": pct(lat, 50), "p95": pct(lat, 95),
                "prompt_tokens": statistics.mean(r["usage"].get("prompt_tokens", 0) for r in recs),
                "completion_tokens": statistics.mean(r["usage"].get("completion_tokens", 0) for r in recs),
                "ttft": ttft,
                "model": recs[0]["model"],
                "top_fails": _top([f for r in recs for f in (r["key_fails"] or r.get("errors_final") or r["errors_raw"])]),
                "samples": [r.get("parsed") or r["raw"] for r in recs[:10]],
            }
            summary.append(row)
            print(f"   valid raw {row['valid_raw']:.0%} -> final {row['valid_final']:.0%} | key pass {row['key_pass']:.0%} | "
                  f"authz viol {row['authz_violations']} | p50 {row['p50']:.1f}s p95 {row['p95']:.1f}s | "
                  f"tok {row['prompt_tokens']:.0f}/{row['completion_tokens']:.0f}", flush=True)
            for f, c in row["top_fails"][:3]:
                print(f"      - {c}x {f}")

    report = Path(args.report) if args.report else REPO / "docs" / "spikes" / f"model-capability-{stamp}.md"
    write_report(report, summary, model, args.mode, args.n)
    print(f"\nreport: {report}\nraw: {raw_path}")


def _top(items: list[str], k: int = 5) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for i in items:
        key = re.sub(r"\[.*?\]|\d+", "#", i)[:90]
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:k]


def write_report(path: Path, summary: list[dict[str, Any]], model: str, mode: str, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Model capability spike — {date.today().isoformat()}",
        "",
        f"A9 project `{model}` (served model: `{summary[0]['model'] if summary else '?'}`), mode `{mode}`, N={n} per case.",
        "Budgets for comparison: `docs/specifications/turn-budget-and-latency.md` §3.",
        "",
        "| case | role | valid raw | valid after 1 repair | key pass | authz viol | p50 s | p95 s | prompt/compl tok | TTFT s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary:
        ttft = f"{r['ttft']:.2f}" if r["ttft"] else "—"
        lines.append(
            f"| {r['case']} | {r['role']} | {r['valid_raw']:.0%} | {r['valid_final']:.0%} | {r['key_pass']:.0%} | "
            f"{r['authz_violations']} | {r['p50']:.1f} | {r['p95']:.1f} | {r['prompt_tokens']:.0f}/{r['completion_tokens']:.0f} | {ttft} |"
        )
    lines += ["", "## Most common failures", ""]
    for r in summary:
        if r["top_fails"]:
            lines.append(f"**{r['case']}**")
            lines += [f"- {c}× {f}" for f, c in r["top_fails"]]
            lines.append("")
    lines += ["## Samples for manual in-character judgement (10 per case)", ""]
    for r in summary:
        lines.append(f"### {r['case']}")
        for i, s in enumerate(r["samples"], 1):
            body = json.dumps(s, ensure_ascii=False, indent=1) if isinstance(s, dict) else str(s)
            lines += [f"<details><summary>sample {i}</summary>", "", "```json", body[:3000], "```", "", "</details>", ""]
    lines += [
        "## Decision (fill in)",
        "",
        "- [ ] (a) proceed as planned",
        "- [ ] (b) proceed with a simplified `conveys[]` / output schema (document in ai-contracts.md §21)",
        "- [ ] (c) change the model / serving stack",
        "- [ ] (d) allow a cloud profile for specific roles",
        "",
        "Record the choice in `docs/DECISIONS.md` and the measured numbers in `docs/HARDWARE-TARGET.md`.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
