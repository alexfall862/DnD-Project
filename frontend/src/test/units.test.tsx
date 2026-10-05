import { render, screen } from "@testing-library/react";
import { parseSse } from "../api/client";
import type { PlayResult } from "../api/types";
import { parseHash, toHash } from "../state";
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
  live: { speakers: [], narration: "", mechanics: [] },
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
    expect(container.querySelector(".roll")).toHaveTextContent("insight: 1d20 +2 = 14");
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
