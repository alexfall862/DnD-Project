import { render, screen } from "@testing-library/react";
import { parseSse } from "../api/client";
import type { PlayResult } from "../api/types";
import { parseHash, toHash } from "../state";
import { applyEvent, fromServer } from "../turns";
import { TurnCard, type FeedTurn } from "../views/Play";

function streamOf(text: string, chunk = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let i = 0;
  return new ReadableStream({
    pull(c) {
      if (i >= bytes.length) return c.close();
      c.enqueue(bytes.slice(i, i + chunk));
      i += chunk;
    },
  });
}

describe("parseSse", () => {
  it("yields events in order even when blocks are split across chunks", async () => {
    const raw =
      'event: accepted\ndata: {"turn_id": "t1"}\n\n' +
      'event: mechanics\ndata: {"action": {"action": "action.search", "status": "succeeded"}}\n\n' +
      'event: narration_delta\ndata: {"text": "Rain "}\n\n' +
      'event: narration_delta\ndata: {"text": "falls."}\n\n';
    const names: string[] = [];
    let text = "";
    for await (const e of parseSse(streamOf(raw))) {
      names.push(e.name);
      if (e.name === "narration_delta") text += e.data.text;
    }
    expect(names).toEqual(["accepted", "mechanics", "narration_delta", "narration_delta"]);
    expect(text).toBe("Rain falls.");
  });
});

describe("hash routes", () => {
  it("round-trips campaign, view and actor", () => {
    const r = { campaignId: "c1", view: "journal" as const, actorId: "a1" };
    expect(parseHash(toHash(r))).toEqual(r);
    expect(parseHash("#/")).toEqual({ campaignId: null, view: "play", actorId: null });
    expect(parseHash("#/c/c1/nonsense").view).toBe("play");
  });
});

const result: PlayResult = {
  turn_id: "turn-1",
  channel: "say",
  narration: "Mira sets the glass down.",
  speakers: [
    { actor_id: "alex", channel: "say", text: "Has Oric been in?" },
    { actor_id: "mira", channel: "say", text: "Not for a week." },
    { actor_id: "elara", channel: "whisper", text: "She's lying." },
  ],
  visible_rolls: [{ expression: "1d20", raw: [12], modifier: 2, total: 14, purpose: "insight" }],
  mechanical_notices: [],
  state_changes: [],
  actions: [
    { action: "action.ask", status: "succeeded", summary: "6a7b-uuid ask → mira: succeeded" },
  ],
  assertions: [],
  time_advanced_seconds: 0,
  versions: {},
  needs_player_input: true,
  metrics: { wall_ms_total: 4200, sync_model_calls: 3 },
  ooc: null,
};

const turn: FeedTurn = {
  key: "k",
  input: { text: "Has Oric been in?", channel: "say", to: [] },
  status: "done",
  live: { sentAt: 0, stages: [], calls: [], speakers: [], narration: "", mechanics: [] },
  result,
};

const names = new Map([
  ["alex", "Alex"],
  ["mira", "Mira"],
  ["elara", "Elara"],
]);

describe("TurnCard", () => {
  it("labels speakers by the names the focus actor knows and never echoes the player", () => {
    const { container } = render(
      <TurnCard turn={turn} names={names} selfId="alex" dev={false} onAnswer={() => {}} />,
    );
    expect(screen.getByText("Mira")).toBeInTheDocument();
    expect(screen.getByText("Not for a week.")).toBeInTheDocument();
    expect(screen.getByText("whispers")).toBeInTheDocument();
    expect(screen.getAllByText("Has Oric been in?")).toHaveLength(1); // the bubble only
    const die = container.querySelector("[data-testid=\"dice-roll\"]");
    expect(die).toHaveTextContent("Insight");
    expect(die).toHaveTextContent("= 14");
  });

  it("keeps developer material out of normal view", () => {
    render(<TurnCard turn={turn} names={names} selfId="alex" dev={false} onAnswer={() => {}} />);
    expect(screen.queryByText(/6a7b-uuid/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Trace" })).toBeNull();
    expect(screen.queryByText(/calls/)).toBeNull();
  });

  it("shows metrics, engine summaries and a trace toggle in dev view", () => {
    render(<TurnCard turn={turn} names={names} selfId="alex" dev onAnswer={() => {}} />);
    expect(screen.getByText(/6a7b-uuid/)).toBeInTheDocument();
    expect(screen.getByText("3 calls")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trace" })).toBeInTheDocument();
  });

  it("offers the clarification candidates", () => {
    const t: FeedTurn = {
      ...turn,
      status: "clarify",
      result: undefined,
      clarification: {
        clarification_id: "c",
        question: "Which one do you mean?",
        candidates: [{ known_as: "the first thief" }, { known_as: "the second thief" }],
        original_input: "Attack him",
      },
    };
    const answers: string[] = [];
    render(<TurnCard turn={t} names={names} dev={false} onAnswer={(a) => answers.push(a)} />);
    screen.getByRole("button", { name: "the second thief" }).click();
    expect(answers).toEqual(["the second thief"]);
  });
});


describe("live turn state", () => {
  it("folds stages and model calls into a timeline", () => {
    let live = { sentAt: 0, stages: [], calls: [], speakers: [], narration: "", mechanics: [] } as FeedTurn["live"];
    live = applyEvent(live, { name: "accepted", data: { turn_id: "t1" } }, 100);
    live = applyEvent(live, { name: "stage", data: { stage: "interpreting", label: "Reading what you do" } }, 120);
    live = applyEvent(live, { name: "model_call", data: { run_id: "r1", role: "intent_interpreter", phase: "started", max_tokens: 1024 } }, 130);
    live = applyEvent(live, { name: "model_call", data: { run_id: "r1", role: "intent_interpreter", phase: "waiting", reason: "busy", wait_s: 5 } }, 140);
    live = applyEvent(live, { name: "model_call", data: { run_id: "r1", role: "intent_interpreter", phase: "finished", status: "ok", completion_tokens: 210 } }, 9000);
    expect(live.turnId).toBe("t1");
    expect(live.stage?.label).toBe("Reading what you do");
    expect(live.calls).toHaveLength(1);
    expect(live.calls[0]).toMatchObject({ status: "ok", startedAt: 130, endedAt: 9000, completion_tokens: 210 });
    expect(live.calls[0].notes[0]).toContain("busy");
  });

  it("restores failed and clarification turns from server history", () => {
    const turns = fromServer([
      { turn_id: "a", created_at: "", input: { text: "x", channel: "do", to: [] }, result: { error: { code: "ACTION_INVALID", message: "bad json" } } as never },
      { turn_id: "b", created_at: "", input: { text: "y", channel: "do", to: [] }, result: { clarification: { clarification_id: "c", question: "Which?", candidates: [], original_input: "y" } } as never },
    ]);
    expect(turns[0]).toMatchObject({ status: "error", error: "ACTION_INVALID: bad json", turnId: "a" });
    expect(turns[1].status).toBe("clarify");
  });
});


describe("dice", () => {
  it("shows the natural die, the total against the DC and the outcome", () => {
    const roll = { id: "r1", expression: "1d20", raw: [13], natural: 13, modifier: 0, total: 21, purpose: "Persuasion", dc: 14, success: true, degree: "success", source: "engine" };
    const t: FeedTurn = { ...turn, result: { ...result, visible_rolls: [roll] } };
    const { container } = render(<TurnCard turn={t} names={names} selfId="alex" dev={false} onAnswer={() => {}} />);
    const die = container.querySelector("[data-testid=\"dice-roll\"]");
    expect(die).toHaveTextContent("13");
    expect(die).toHaveTextContent("= 21 vs 14");
    expect(die).toHaveTextContent("Success");
    expect(screen.queryByText(/engine dice/)).toBeNull(); // the certificate is dev-only
  });

  it("asks for the roll with the check, the target and the stakes", () => {
    const t: FeedTurn = {
      ...turn,
      result: {
        ...result,
        visible_rolls: [],
        roll_request: {
          id: "pr1",
          prompt: "This calls for a Persuasion check",
          checks: [{ label: "Persuasion", kind: "persuade", target_known_as: "Mira", die: "1d20", bonus: 5, dc: 14, attribute: "attr.presence", skill: "skill.persuasion", stakes: { success: "She helps.", failure: "She is wary.", retry: "Try another way." } }],
        },
      },
    };
    const decisions: string[] = [];
    render(<TurnCard turn={t} names={names} selfId="alex" dev={false} onAnswer={() => {}} onRoll={(d) => decisions.push(d)} />);
    expect(screen.getByText(/Persuasion check/)).toBeInTheDocument();
    expect(screen.getByText("She is wary.")).toBeInTheDocument();
    screen.getByRole("button", { name: "Roll" }).click();
    screen.getByRole("button", { name: "Reconsider" }).click();
    expect(decisions).toEqual(["roll", "reconsider"]);
  });
});
