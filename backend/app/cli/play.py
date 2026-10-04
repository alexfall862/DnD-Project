"""Terminal play harness (Milestone 06d; api-contracts §9–§12, human-visibility §2,
turn-budget §6–§7).

    uv run python -m app.cli.play --new            # seed the Red Lantern and play as Alex
    uv run python -m app.cli.play --campaign <id>  # resume

It uses the HTTP API only — the same boundary the browser client will use — and never parses
narration for state: it prints what the API returns, mechanics first, then speaker-labelled
AI lines, then the narration stream, then a status line with the turn's metrics.

Input:  bare text = auto channel; `/do`, `/say`, `/think`, `/ooc` prefixes; `/whisper <name>
text`; `/scene`, `/inventory`, `/beliefs`, `/journal`, `/encyclopedia`; `/end` (scene end,
debug); `/debug events|perspective <name>|compare|context <model_run>|beliefs <name>|
metrics|runs`; `/quit`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any

import httpx

API = "/api/v1"
HELP = (
    "commands: /do /say /think /ooc <text> | /whisper <name> <text> | /scene /inventory "
    "/beliefs /journal /encyclopedia | /end | /debug events|perspective <name>|compare|"
    "context <model_run>|beliefs <name>|metrics|runs | /quit"
)


class HarnessError(RuntimeError):
    pass


def _someone(raw: Any) -> str:
    """An entity this character cannot name shows as 'someone'; free text stays as is."""
    if not raw:
        return ""
    s = str(raw)
    return "someone" if len(s) == 36 and s.count("-") == 4 else s


class Harness:
    def __init__(self, client: httpx.AsyncClient, out: Callable[[str], None] = print) -> None:
        self.client = client
        self.out = out
        self.campaign_id: str | None = None
        self.scene_id: str | None = None
        self.actor_id: str | None = None
        self.actor_name: str | None = None
        self.actors: dict[str, dict[str, Any]] = {}  # name -> row
        self.last_metrics: dict[str, Any] = {}
        self.last_result: dict[str, Any] | None = None
        self.last_events: list[tuple[str, dict[str, Any]]] = []

    # -- setup ------------------------------------------------------------------------------

    async def new_campaign(self, *, actor: str | None = None) -> None:
        r = await self.client.post(f"{API}/debug/seed-demo")
        self._check(r, "seed-demo (needs DEBUG_MODE=true)")
        seed = r.json()
        self.campaign_id = seed["campaign_id"]
        self.scene_id = seed["scene_id"]
        await self.load_campaign(self.campaign_id, actor=actor)
        self.out(f"new campaign {self.campaign_id} (scene {self.scene_id})")

    async def load_campaign(self, campaign_id: str, *, actor: str | None = None) -> None:
        self.campaign_id = campaign_id
        r = await self.client.get(f"{API}/debug/campaigns/{campaign_id}/actors")
        self._check(r, "actors (needs DEBUG_MODE=true)")
        self.actors = {row["name"]: row for row in r.json()}
        humans = [row for row in self.actors.values() if row["controller"] == "human"]
        if actor:
            row = self._actor(actor)
            if row["controller"] != "human":
                raise HarnessError(f"{actor} is not human-controlled")
        elif humans:
            row = humans[0]
        else:
            raise HarnessError("no human-controlled actor in this campaign")
        self.actor_id, self.actor_name = row["actor_id"], row["name"]
        self.scene_id = row.get("scene_id") or self.scene_id
        self.out(f"playing as {self.actor_name} ({self.actor_id})")

    def _actor(self, name: str) -> dict[str, Any]:
        for n, row in self.actors.items():
            if n.lower() == name.lower() or n.lower().split()[0] == name.lower():
                return row
        raise HarnessError(f"unknown actor {name!r}; known: {', '.join(self.actors)}")

    @staticmethod
    def _check(r: httpx.Response, what: str) -> None:
        if r.status_code >= 400:
            try:
                err = r.json().get("error", r.json())
            except ValueError:
                err = r.text
            raise HarnessError(f"{what}: {r.status_code} {err}")

    # -- views --------------------------------------------------------------------------------

    async def show_scene(self) -> dict[str, Any]:
        r = await self.client.get(
            f"{API}/campaigns/{self.campaign_id}/scene", params={"actor_id": self.actor_id}
        )
        self._check(r, "scene")
        v = r.json()
        self.scene_id = v["scene_id"]
        others = ", ".join(
            f"{p['known_as']}{' [' + p['zone'] + ']' if p.get('zone') else ''}"
            for p in v["participants"]
            if not p["is_self"]
        )
        self.out(
            f"[{v['location_known_as'] or 'an unfamiliar place'} | {v['scene_type']} | tick "
            f"{v['world_tick']} | you are at {v['your_zone'] or 'here'}]"
        )
        self.out(f"present: {others or 'no one you can see'}")
        return v

    async def show_inventory(self) -> None:
        r = await self.client.get(f"{API}/characters/{self.actor_id}/inventory")
        self._check(r, "inventory")
        for i in r.json():
            props = i.get("properties") or {}
            self.out(
                f"- {i['name'] or i['template_key']}{' (equipped)' if i['equipped'] else ''}"
                + (f": {props.get('description')}" if props.get("description") else "")
            )
        if not r.json():
            self.out("- nothing")

    async def show_beliefs(self) -> None:
        r = await self.client.get(f"{API}/characters/{self.actor_id}/beliefs")
        self._check(r, "beliefs")
        for b in r.json():
            p = b["proposition"]
            if p.get("predicate") == "asserted":
                continue  # "X said P" meta-beliefs are noise at the table
            subj = b.get("subject_known_as") or _someone(p.get("subject_entity_id"))
            obj = b.get("object_known_as") or _someone(p.get("object_entity_id"))
            self.out(
                f"- {b['belief_type']} {b['confidence']:.2f}: {subj} {p.get('predicate')} {obj}"
                + (f" {p['value']}" if p.get("value") not in (None, "") else "")
                + (f" (from {b['source_known_as']})" if b.get("source_known_as") else "")
            )

    async def show_journal(self) -> None:
        r = await self.client.get(f"{API}/characters/{self.actor_id}/journal")
        self._check(r, "journal")
        for e in r.json():
            self.out(f"## {e['title'] or e['entry_type']} (tick {e['game_tick']})")
            self.out(e["body"])
        if not r.json():
            self.out("(no entries yet)")

    async def show_encyclopedia(self) -> None:
        r = await self.client.get(f"{API}/characters/{self.actor_id}/encyclopedia")
        self._check(r, "encyclopedia")
        for e in r.json():
            self.out(f"- [{e['category']}] {e['summary']}")
            for kind, lines in e["knowledge"].items():
                for line in lines:
                    self.out(f"    {kind}: {line}")

    # -- play -----------------------------------------------------------------------------------

    async def play(
        self, text: str, *, channel: str = "auto", targets: list[str] | None = None
    ) -> dict[str, Any] | None:
        body = {
            "actor_id": self.actor_id,
            "text": text,
            "channel": channel,
            "target_actor_ids": targets or [],
        }
        self.last_events = []
        narration: list[str] = []
        result: dict[str, Any] | None = None
        async with self.client.stream(
            "POST",
            f"{API}/campaigns/{self.campaign_id}/play",
            json=body,
            headers={"accept": "text/event-stream"},
        ) as r:
            if r.status_code >= 400:
                await r.aread()
                self._check(r, "play")
            name = None
            async for line in r.aiter_lines():
                if line.startswith("event: "):
                    name = line[7:].strip()
                elif line.startswith("data: ") and name:
                    payload = json.loads(line[6:])
                    self.last_events.append((name, payload))
                    result = self._render(name, payload, narration) or result
                    name = None
        if narration:
            if self.out is print:
                print("")  # end the streamed line
            else:
                self.out("".join(narration))  # buffered sinks get the whole narration once
        self.last_result = result
        return result

    def _render(self, name: str, p: dict[str, Any], narration: list[str]) -> dict[str, Any] | None:
        if name == "accepted":
            self.out(f"… turn {p['turn_id'][:8]}")
        elif name == "mechanics":
            if "action" in p:
                a = p["action"]
                self.out(
                    f"  ⚙ {a['action']} → {a['status']}"
                    + (f" ({a['summary']})" if a.get("summary") else "")
                )
            if "speech" in p:
                s = p["speech"]
                self.out(
                    f"  ⚙ you {s['channel']}: {s['recipients']} hear you ({s['claims']} claim(s))"
                )
            if "ai_turn" in p:
                t = p["ai_turn"]
                acts = "; ".join(f"{x['action']}→{x['status']}" for x in t["actions"])
                self.out(f"  ⚙ {self._name_of(t['actor'])} ({t['source']}): {acts}")
            for roll in p.get("visible_rolls", []):
                self.out(f"  🎲 {roll['purpose']}: {roll['expression']} = {roll['total']}")
            for c in p.get("state_changes", []):
                self.out(f"  Δ {c['resource']}: {c['before']} → {c['after']}")
        elif name == "speaker":
            self.out(f'  {self._name_of(p["actor"])}: "{p["text"]}"')
        elif name == "reaction":
            pass
        elif name == "narration_delta":
            narration.append(p["text"])
            if self.out is print:  # terminal: stream the tokens; otherwise buffer (see play)
                if len(narration) == 1:
                    print("")
                sys.stdout.write(p["text"])
                sys.stdout.flush()
        elif name == "complete":
            m = p.get("metrics", {})
            self.last_metrics = m
            self.out(
                f"[{m.get('wall_ms_total')} ms | calls {m.get('sync_model_calls')}"
                f"+{m.get('background_model_calls', 0)} bg | first output "
                f"{m.get('ms_to_first_output')} ms | narration "
                f"{m.get('ms_to_first_narration_token')} ms | "
                f"{', '.join(f'{k}×{v}' for k, v in (m.get('calls_by_role') or {}).items())}"
                + (
                    f" | degraded: {', '.join(m['degradation_steps'])}"
                    if m.get("degradation_steps")
                    else ""
                )
                + "]"
            )
        elif name == "result":
            for n in p.get("mechanical_notices", []):
                self.out(f"  · {n}")
            for a in p.get("assertions", []):
                self.out(f"  ✎ {a['class']} {a['result']}: {a.get('note') or ''}")
            if p.get("ooc"):
                self.out(f"  (OOC) {p['ooc']}")
            return p
        elif name == "error":
            self.out(f"  ✗ {p.get('code')}: {p.get('message') or p.get('question') or ''}")
            if p.get("candidates"):
                self.out("    candidates: " + ", ".join(c["ref"] for c in p["candidates"]))
            return {"error": p}
        return None

    def _name_of(self, actor_id: str) -> str:
        for n, row in self.actors.items():
            if row["actor_id"] == actor_id:
                return n
        return actor_id[:8]

    # -- debug ----------------------------------------------------------------------------------

    async def debug(self, args: list[str]) -> None:
        if not args:
            self.out(
                "debug: events | perspective <name> | compare | context <model_run> | "
                "beliefs <name> | metrics | runs"
            )
            return
        sub, rest = args[0], args[1:]
        base = f"{API}/debug"
        if sub == "events":
            r = await self.client.get(
                f"{base}/campaigns/{self.campaign_id}/events",
                params={"limit": int(rest[0]) if rest else 30},
            )
            self._check(r, "debug events (DEBUG_MODE off?)")
            for e in r.json():
                self.out(
                    f"  #{e['sequence']} t{e['tick']} {e['type']} {json.dumps(e['payload'])[:120]}"
                )
        elif sub == "perspective":
            row = self._actor(rest[0])
            r = await self.client.get(f"{base}/actors/{row['actor_id']}/perspective")
            self._check(r, "debug perspective")
            self.out(json.dumps(r.json(), indent=1)[:4000])
        elif sub == "compare":
            ids = ",".join(
                row["actor_id"]
                for row in self.actors.values()
                if row["controller"] in ("human", "ai")
            )
            r = await self.client.get(
                f"{base}/campaigns/{self.campaign_id}/perspectives/compare",
                params={"actor_ids": ids},
            )
            self._check(r, "debug compare")
            self.out(json.dumps(r.json(), indent=1)[:6000])
        elif sub == "context":
            r = await self.client.get(f"{base}/model-runs/{rest[0]}/context")
            self._check(r, "debug context")
            d = r.json()
            self.out(f"# {d['role']} {d['status']} prompt {d['prompt_id']} v{d['prompt_version']}")
            self.out(d.get("rendered_context") or "(no context)")
            self.out("# raw output\n" + (d.get("raw_output") or ""))
        elif sub == "beliefs":
            row = self._actor(rest[0])
            r = await self.client.get(f"{base}/actors/{row['actor_id']}/perspective")
            self._check(r, "debug beliefs")
            for b in r.json().get("beliefs", []):
                kind = b.get("type") or b.get("belief_type")
                self.out(f"  {kind} {b['confidence']:.2f} {json.dumps(b['proposition'])}")
        elif sub == "metrics":
            r = await self.client.get(f"{base}/campaigns/{self.campaign_id}/metrics")
            self._check(r, "debug metrics")
            for m in r.json():
                self.out(
                    f"  {m['turn_id'][:8]} {m['wall_ms_total']} ms calls {m['sync_model_calls']} "
                    f"{json.dumps(m['calls_by_role'])} {m['degradation_steps']}"
                )
        elif sub == "runs":
            r = await self.client.get(f"{base}/campaigns/{self.campaign_id}/model-runs")
            self._check(r, "debug runs")
            for m in r.json():
                self.out(
                    f"  {m['model_run_id']} {m['role']} {m['status']} {m['latency_ms']} ms "
                    f"{m['prompt_tokens']}+{m['completion_tokens']}"
                )
        else:
            self.out(f"unknown debug command {sub!r}")

    async def end_scene(self) -> None:
        r = await self.client.post(
            f"{API}/debug/campaigns/{self.campaign_id}/scenes/{self.scene_id}/end"
        )
        self._check(r, "end scene (debug)")
        m = r.json()
        self.out(
            f"scene ended: {json.dumps(m.get('checkpoints', []))[:300]} "
            f"journals {m.get('journals')}"
        )

    # -- dispatch ---------------------------------------------------------------------------------

    async def handle(self, line: str) -> bool:
        """Returns False to quit."""
        line = line.strip()
        if not line:
            return True
        if line in ("/quit", "/exit"):
            return False
        if line in ("/help", "?"):
            self.out(HELP)
            return True
        if line.startswith("/debug"):
            await self.debug(line.split()[1:])
            return True
        if line == "/scene":
            await self.show_scene()
            return True
        if line == "/inventory":
            await self.show_inventory()
            return True
        if line == "/beliefs":
            await self.show_beliefs()
            return True
        if line == "/journal":
            await self.show_journal()
            return True
        if line == "/encyclopedia":
            await self.show_encyclopedia()
            return True
        if line == "/end":
            await self.end_scene()
            return True
        if line.startswith("/whisper "):
            parts = line.split(" ", 2)
            if len(parts) < 3:
                self.out("usage: /whisper <name> <text>")
                return True
            row = self._actor(parts[1])
            await self.play(parts[2], channel="whisper", targets=[row["actor_id"]])
            return True
        await self.play(line)  # /do, /say, /think, /ooc prefixes are understood by the API
        return True


async def amain(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI TTRPG terminal harness (HTTP client)")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--campaign", help="campaign id to resume")
    ap.add_argument("--new", action="store_true", help="seed a new Red Lantern campaign")
    ap.add_argument("--actor", help="human actor name to play (default: the first human)")
    ap.add_argument("--script", help="file with one command per line (replay)")
    args = ap.parse_args(argv)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=600) as client:
        h = Harness(client)
        try:
            if args.new or not args.campaign:
                await h.new_campaign(actor=args.actor)
            else:
                await h.load_campaign(args.campaign, actor=args.actor)
            await h.show_scene()
        except (HarnessError, httpx.HTTPError) as exc:
            print(f"error: {exc}")
            return 1
        print(HELP)
        lines = None
        if args.script:
            with open(args.script, encoding="utf-8") as f:
                lines = [ln.rstrip("\n") for ln in f]
        while True:
            try:
                if lines is not None:
                    if not lines:
                        break
                    line = lines.pop(0)
                    print(f"{h.actor_name}> {line}")
                else:
                    line = await asyncio.to_thread(input, f"{h.actor_name}> ")
            except (EOFError, KeyboardInterrupt):
                break
            try:
                if not await h.handle(line):
                    break
            except (HarnessError, httpx.HTTPError) as exc:
                print(f"error: {type(exc).__name__}: {exc}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
