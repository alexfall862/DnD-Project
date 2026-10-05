import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ApiError, ClarificationNeeded, api, playStream, type StreamEvent } from "../api/client";
import type {
  Channel,
  Clarification,
  FeedEntry,
  Participant,
  PartyMember,
  PlayResult,
  SceneView,
  Uuid,
} from "../api/types";
import * as I from "../components/Icons";
import { TraceView } from "../components/Trace";
import { useApp } from "../state";

// ---- feed model ----------------------------------------------------------------------------------

export interface FeedTurn {
  key: string;
  input: { text: string; channel: Channel; to: string[] };
  status: "streaming" | "done" | "error" | "clarify";
  live: { speakers: { actor: Uuid; text: string }[]; narration: string; mechanics: string[] };
  result?: PlayResult;
  error?: string;
  clarification?: Clarification;
}

// the feed lives on the server (GET /characters/{id}/feed): any device shows the same history
function fromServer(entries: FeedEntry[]): FeedTurn[] {
  return entries.map((e) => ({
    key: e.turn_id,
    input: e.input,
    status: "done" as const,
    live: { speakers: [], narration: "", mechanics: [] },
    result: e.result,
  }));
}

const CHANNELS: { id: Channel; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Describe what you do or say" },
  { id: "do", label: "Do", hint: "An action: I search the desk…" },
  { id: "say", label: "Say", hint: "Spoken aloud to the scene" },
  { id: "whisper", label: "Whisper", hint: "Only the chosen listener hears" },
  { id: "private", label: "Private", hint: "Your character's private thought" },
  { id: "ooc", label: "OOC", hint: "Out of character: ask the table, not the world" },
];

// ---- mechanics summary of a streamed `mechanics` event ------------------------------------------

function mechanicsLine(data: Record<string, unknown>): string | null {
  const a = data.action as Record<string, unknown> | undefined;
  if (a) return `${String(a.action).replace("action.", "")} → ${a.status}`;
  const t = data.ai_turn as Record<string, unknown> | undefined;
  if (t) {
    const acts = (t.actions as Record<string, unknown>[] | undefined) ?? [];
    return acts.map((x) => `${String(x.action).replace("action.", "")} → ${x.status}`).join("; ") || null;
  }
  return null;
}

// ---- view ----------------------------------------------------------------------------------------

export function PlayView() {
  const { campaign, focusActorId, focusName, dev, version, bump } = useApp();
  const [scene, setScene] = useState<SceneView | null>(null);
  const [party, setParty] = useState<PartyMember[]>([]);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const cid = campaign?.id ?? "";
  const [feedError, setFeedError] = useState<string | null>(null);
  useEffect(() => {
    if (!cid || !focusActorId) return;
    let live = true;
    api.feed(focusActorId).then(
      (entries) => {
        if (!live) return;
        setFeed((f) => [...fromServer(entries), ...f.filter((t) => t.status !== "done")]);
        setFeedError(null);
      },
      (e: Error) => live && setFeedError(e.message),
    );
    return () => {
      live = false;
    };
  }, [cid, focusActorId]);

  useEffect(() => {
    if (!cid || !focusActorId) return;
    api.scene(cid, focusActorId).then(
      (s) => {
        setScene(s);
        setSceneError(null);
      },
      (e: Error) => setSceneError(e.message),
    );
    api.party(cid, focusActorId).then(setParty, () => setParty([]));
  }, [cid, focusActorId, version]);

  // speaker labels: the names the focus actor knows (scene participants, then party)
  const names = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of party) m.set(p.actor_id, p.known_as === "you" ? focusName ?? "You" : p.known_as);
    for (const p of scene?.participants ?? [])
      if (p.actor_id) m.set(p.actor_id, p.is_self ? focusName ?? "You" : p.known_as);
    return m;
  }, [scene, party, focusName]);

  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [feed]);

  const send = useCallback(
    async (text: string, channel: Channel, targets: Participant[], clarificationId?: string) => {
      if (!cid || !focusActorId) return;
      const key = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const turn: FeedTurn = {
        key,
        input: { text, channel, to: targets.map((t) => t.known_as) },
        status: "streaming",
        live: { speakers: [], narration: "", mechanics: [] },
      };
      setFeed((f) => [...f.filter((t) => t.status !== "clarify"), turn]);
      setBusy(true);
      const update = (fn: (t: FeedTurn) => FeedTurn) =>
        setFeed((f) => f.map((t) => (t.key === key ? fn(t) : t)));
      const onEvent = (e: StreamEvent) => {
        if (e.name === "narration_delta")
          update((t) => ({ ...t, live: { ...t.live, narration: t.live.narration + e.data.text } }));
        else if (e.name === "speaker")
          update((t) => ({ ...t, live: { ...t.live, speakers: [...t.live.speakers, e.data] } }));
        else if (e.name === "mechanics") {
          const line = mechanicsLine(e.data);
          if (line) update((t) => ({ ...t, live: { ...t.live, mechanics: [...t.live.mechanics, line] } }));
        }
      };
      try {
        const result = await playStream(
          cid,
          {
            actor_id: focusActorId,
            text,
            channel,
            target_actor_ids: targets.map((t) => t.actor_id).filter((x): x is string => !!x),
            clarification_id: clarificationId,
          },
          onEvent,
        );
        setFeed((f) => f.map((t) => (t.key === key ? { ...t, status: "done" as const, result } : t)));
        bump();
      } catch (err) {
        if (err instanceof ClarificationNeeded) {
          update((t) => ({ ...t, status: "clarify", clarification: err.clarification }));
        } else {
          const msg =
            err instanceof ApiError ? `${err.code}: ${err.message}` : (err as Error).message;
          update((t) => ({ ...t, status: "error", error: msg }));
        }
      } finally {
        setBusy(false);
      }
    },
    [cid, focusActorId, bump],
  );

  if (!campaign) return null;
  if (!focusActorId)
    return (
      <div className="page">
        <div className="empty">This campaign has no player character yet.</div>
      </div>
    );

  const others = (scene?.participants ?? []).filter((p) => !p.is_self && p.actor_id);
  return (
    <div className="play">
      <div className="scene-strip" aria-label="Current scene">
        <span className="place">{scene?.location_known_as ?? "Somewhere unfamiliar"}</span>
        {scene?.your_zone && <span className="chip">{scene.your_zone}</span>}
        <span className="muted">
          {others.length ? `with ${others.map((p) => p.known_as).join(", ")}` : "alone"}
        </span>
        {sceneError && <span className="chip bad">{sceneError}</span>}
        {feedError && <span className="chip bad">history: {feedError}</span>}
      </div>
      <div className="feed" ref={feedRef}>
        <div className="feed-inner">
          {feed.length === 0 && (
            <div className="empty">
              <p>The scene is yours. What do you do?</p>
            </div>
          )}
          {feed.map((t) => (
            <TurnCard
              key={t.key}
              turn={t}
              names={names}
              selfId={focusActorId}
              dev={dev}
              onAnswer={(answer) =>
                t.clarification &&
                send(answer, t.input.channel, [], t.clarification.clarification_id)
              }
            />
          ))}
        </div>
      </div>
      <Composer busy={busy} others={others} onSend={send} />
    </div>
  );
}

// ---- one turn -------------------------------------------------------------------------------------

export function TurnCard({
  turn,
  names,
  selfId,
  dev,
  onAnswer,
}: {
  turn: FeedTurn;
  names: Map<string, string>;
  selfId?: string | null;
  dev: boolean;
  onAnswer: (answer: string) => void;
}) {
  const [traceOpen, setTraceOpen] = useState(false);
  const r = turn.result;
  const label = (id: string) => names.get(id) ?? "Someone";
  const speakers = r
    ? r.speakers.filter((s) => s.text)
    : turn.live.speakers.map((s) => ({ actor_id: s.actor, text: s.text, channel: "say" }));
  // the player's own line is the bubble above; do not echo it as a speaker
  const ownEcho = (s: { actor_id: string; text: string }) =>
    s.actor_id === selfId || s.text.trim() === turn.input.text.trim();
  const narration = r ? r.narration : turn.live.narration;
  const ch = turn.input.channel;
  return (
    <article className="turn" aria-busy={turn.status === "streaming"}>
      <div className={`player-line ${ch === "whisper" ? "whisper" : ""} ${ch === "ooc" ? "ooc" : ""}`}>
        {ch !== "auto" && (
          <span className="ch">
            {ch}
            {turn.input.to.length ? ` → ${turn.input.to.join(", ")}` : ""}
          </span>
        )}
        {turn.input.text}
      </div>

      {r ? (
        <Mechanics result={r} dev={dev} />
      ) : (
        turn.live.mechanics.length > 0 && (
          <div className="mechanics">
            {turn.live.mechanics.map((m, i) => (
              <span key={i}>⚙ {m}</span>
            ))}
          </div>
        )
      )}

      {speakers
        .filter((s) => !ownEcho(s))
        .map((s, i) => (
          <div className="speech" key={i}>
            <span className="who">
              {label(s.actor_id)}
              {s.channel === "whisper" && <span className="ch">whispers</span>}
            </span>
            <q>{s.text}</q>
          </div>
        ))}

      {r?.ooc && <div className="ooc-reply">{r.ooc}</div>}

      {(narration || turn.status === "streaming") && (
        <div className="narration">
          {narration}
          {turn.status === "streaming" && narration && <span className="cursor" />}
        </div>
      )}
      {turn.status === "streaming" && !narration && (
        <div className="thinking" role="status">
          <span className="dots">
            <span />
            <span />
            <span />
          </span>
          {turn.live.mechanics.length ? "The world responds…" : "Working out what happens…"}
        </div>
      )}

      {turn.status === "clarify" && turn.clarification && (
        <Clarify c={turn.clarification} onAnswer={onAnswer} />
      )}
      {turn.status === "error" && <div className="error-box">{turn.error}</div>}

      {r && dev && (
        <div className="turn-meta">
          <span className="chip dev">
            {((r.metrics.wall_ms_total ?? 0) / 1000).toFixed(1)} s
          </span>
          <span className="chip dev">{r.metrics.sync_model_calls ?? 0} calls</span>
          {(r.metrics.degradation_steps ?? []).map((d) => (
            <span className="chip warn" key={d}>
              {d}
            </span>
          ))}
          <button type="button" className="btn small dev" onClick={() => setTraceOpen((o) => !o)}>
            {traceOpen ? "Hide trace" : "Trace"}
          </button>
        </div>
      )}
      {r && dev && traceOpen && <TraceView turnId={r.turn_id} />}
    </article>
  );
}

function Mechanics({ result, dev }: { result: PlayResult; dev: boolean }) {
  const lines: JSX.Element[] = [];
  result.actions.forEach((a, i) => {
    const failed = a.status === "invalid" || a.status === "failed";
    lines.push(
      <span key={`a${i}`} className={failed ? "muted" : undefined}>
        ⚙ {a.action.replace("action.", "")}
        {a.target ? ` · ${a.target}` : ""} → {a.status}
        {dev && a.summary ? ` · ${a.summary}` : ""}
      </span>,
    );
  });
  result.visible_rolls.forEach((r, i) =>
    lines.push(
      <span key={`r${i}`} className="roll">
        <I.Dice style={{ width: 14, height: 14, verticalAlign: "-2px" }} /> {r.purpose}: {r.expression}
        {r.modifier ? ` ${r.modifier > 0 ? "+" : ""}${r.modifier}` : ""} = <b>{r.total}</b>
      </span>,
    ),
  );
  result.state_changes.forEach((c, i) =>
    lines.push(
      <span key={`s${i}`}>
        Δ {String(c.resource ?? "").replace("resource.", "")}: {String(c.before)} → {String(c.after)}
      </span>,
    ),
  );
  result.mechanical_notices.forEach((n, i) =>
    lines.push(
      <span key={`n${i}`} className="muted">
        {n.length > 240 ? `${n.slice(0, 240)}…` : n}
      </span>,
    ),
  );
  if (result.time_advanced_seconds >= 60)
    lines.push(
      <span key="t" className="muted">
        ⏱ {Math.round(result.time_advanced_seconds / 60)} min pass
      </span>,
    );
  if (!lines.length) return null;
  return <div className="mechanics">{lines}</div>;
}

function Clarify({ c, onAnswer }: { c: Clarification; onAnswer: (a: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div className="clarify stack">
      <strong>{c.question}</strong>
      <div className="row">
        {c.candidates.map((x, i) => {
          const name = String(x.known_as ?? x.label ?? x.ref ?? `option ${i + 1}`);
          return (
            <button key={i} type="button" className="btn small" onClick={() => onAnswer(name)}>
              {name}
            </button>
          );
        })}
      </div>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) onAnswer(text.trim());
        }}
      >
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Or answer in your own words"
          aria-label="Clarification answer"
          style={{ flex: 1 }}
        />
        <button className="btn small" type="submit">
          Answer
        </button>
      </form>
    </div>
  );
}

// ---- composer --------------------------------------------------------------------------------------

function Composer({
  busy,
  others,
  onSend,
}: {
  busy: boolean;
  others: Participant[];
  onSend: (text: string, channel: Channel, targets: Participant[]) => void;
}) {
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<Channel>("auto");
  const [target, setTarget] = useState<string>("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const whisperTarget = others.find((o) => o.actor_id === target);
  const needsTarget = channel === "whisper" && !whisperTarget;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || busy || needsTarget) return;
    onSend(t, channel, channel === "whisper" && whisperTarget ? [whisperTarget] : []);
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };
  const hint = CHANNELS.find((c) => c.id === channel)?.hint ?? "";
  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="composer-inner">
        <div className="channels" role="group" aria-label="Channel">
          {CHANNELS.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={channel === c.id}
              onClick={() => setChannel(c.id)}
              title={c.hint}
            >
              {c.label}
            </button>
          ))}
        </div>
        {channel === "whisper" && (
          <select
            aria-label="Whisper to"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">Whisper to…</option>
            {others.map((o) => (
              <option key={o.actor_id ?? o.entity_id} value={o.actor_id ?? ""}>
                {o.known_as}
              </option>
            ))}
          </select>
        )}
        <div className="input-row">
          <textarea
            ref={ref}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            placeholder={hint}
            aria-label="What do you do?"
            enterKeyHint="send"
          />
          <button
            className="btn primary send"
            type="submit"
            disabled={busy || !text.trim() || needsTarget}
            aria-label="Send"
          >
            <I.Send style={{ width: 20, height: 20 }} />
          </button>
        </div>
      </div>
    </form>
  );
}
