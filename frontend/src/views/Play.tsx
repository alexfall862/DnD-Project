import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../api/client";
import type { Channel, Clarification, Participant, PartyMember, PlayResult, SceneView } from "../api/types";
import * as I from "../components/Icons";
import { DiceRoll, RollRequestCard } from "../components/Dice";
import { TraceView } from "../components/Trace";
import { useApp } from "../state";
import { useNow, useTurns, type CallInfo, type FeedTurn } from "../turns";

export type { FeedTurn } from "../turns";

const CHANNELS: { id: Channel; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Describe what you do or say" },
  { id: "do", label: "Do", hint: "An action: I search the desk…" },
  { id: "say", label: "Say", hint: "Spoken aloud to the scene" },
  { id: "whisper", label: "Whisper", hint: "Only the chosen listener hears" },
  { id: "private", label: "Private", hint: "Your character's private thought" },
  { id: "ooc", label: "OOC", hint: "Out of character: ask the table, not the world" },
];

// ---- view ----------------------------------------------------------------------------------------

export function PlayView() {
  const { campaign, focusActorId, focusName, dev, version, reloadCampaign } = useApp();
  const [rolling, setRolling] = useState<string | null>(null);
  const { feed, feedError, busy, send } = useTurns();
  const [scene, setScene] = useState<SceneView | null>(null);
  const [party, setParty] = useState<PartyMember[]>([]);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const cid = campaign?.id ?? "";

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
          {feed.map((t, i) => (
            <TurnCard
              key={t.key}
              turn={t}
              names={names}
              selfId={focusActorId}
              dev={dev}
              answerable={i === feed.length - 1 && !busy}
              rolling={rolling !== null && rolling === t.result?.roll_request?.id}
              onAnswer={(answer) =>
                t.clarification &&
                send(answer, t.input.channel, [], t.clarification.clarification_id)
              }
              onRoll={async (decision, auto) => {
                const id = t.result?.roll_request?.id;
                if (!id) return;
                if (auto && campaign) {
                  await api.patchSettings(campaign.id, { dice_mode: "auto" });
                  await reloadCampaign();
                }
                if (decision === "roll") setRolling(id);
                try {
                  await send(decision === "roll" ? "🎲 Roll" : "Reconsider", "do", [], undefined, { id, decision });
                } finally {
                  setRolling(null);
                }
              }}
            />
          ))}
        </div>
      </div>
      <Composer
        busy={busy}
        others={others}
        partyIds={party.map((m) => m.actor_id)}
        onSend={send}
      />
    </div>
  );
}

// ---- live status of a turn in flight ----------------------------------------------------------------

const secs = (ms: number) => `${(Math.max(0, ms) / 1000).toFixed(1)} s`;

export function LiveStatus({ turn, dev }: { turn: FeedTurn; dev: boolean }) {
  const now = useNow(turn.status === "streaming");
  const live = turn.live;
  const end = turn.endedAt ?? now;
  const running = live.calls.filter((c) => c.phase !== "finished");
  const waiting = running.flatMap((c) => c.notes.filter((n) => n.startsWith("waiting")));
  const label = live.stage?.label ?? (live.acceptedAt ? "Starting" : "Sending");
  return (
    <div className="live" role="status" aria-live="polite">
      <div className="thinking">
        {turn.status === "streaming" && (
          <span className="dots">
            <span />
            <span />
            <span />
          </span>
        )}
        <span>
          {turn.status === "streaming" ? `${label}…` : "Stopped"} <span className="muted">· {secs(end - live.sentAt)}</span>
        </span>
        {waiting.length > 0 && <span className="chip warn">{waiting[waiting.length - 1].replace("waiting: ", "")}</span>}
      </div>
      {dev && <CallTimeline turn={turn} now={end} />}
    </div>
  );
}

function CallTimeline({ turn, now }: { turn: FeedTurn; now: number }) {
  const live = turn.live;
  return (
    <div className="trace small" data-testid="live-calls">
      <span className="label">Live · dev only</span>
      <div className="mono">
        request sent {new Date(live.sentAt).toLocaleTimeString()}
        {live.acceptedAt ? ` · accepted after ${secs(live.acceptedAt - live.sentAt)}` : " · not yet accepted"}
        {live.turnId ? ` · turn ${live.turnId.slice(0, 8)}` : ""}
      </div>
      {live.stages.length > 0 && (
        <div className="row">
          {live.stages.map((s, i) => (
            <span key={i} className="chip dev">
              {s.label} +{secs(s.at - live.sentAt)}
            </span>
          ))}
        </div>
      )}
      {live.calls.length === 0 ? (
        <span className="muted">No model call yet.</span>
      ) : (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Call</th>
                <th>State</th>
                <th>Time</th>
                <th>Tokens</th>
                <th>Sent</th>
              </tr>
            </thead>
            <tbody>
              {live.calls.map((c) => (
                <CallRow key={c.run_id} c={c} now={now} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CallRow({ c, now }: { c: CallInfo; now: number }) {
  const [open, setOpen] = useState(false);
  const state = c.phase === "finished" ? c.status ?? "done" : c.phase === "started" ? "running" : c.phase;
  return (
    <>
      <tr>
        <td className="mono">{c.role}</td>
        <td>
          <span className={`chip ${state === "ok" ? "ok" : state === "failed" || state === "invalid" ? "bad" : state === "running" ? "dev" : "warn"}`}>
            {state}
          </span>
          {c.notes.map((n, i) => (
            <div key={i} className="muted">
              {n}
            </div>
          ))}
        </td>
        <td className="mono">{secs((c.endedAt ?? now) - c.startedAt)}</td>
        <td className="mono">
          {c.prompt_tokens ?? c.context_tokens ?? "?"}→{c.completion_tokens ?? "…"}/{c.max_tokens ?? "?"}
        </td>
        <td>
          <button type="button" className="btn small dev" onClick={() => setOpen((o) => !o)}>
            {open ? "Hide" : "What was sent"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5}>
            <SentContext runId={c.run_id} />
          </td>
        </tr>
      )}
    </>
  );
}

function SentContext({ runId }: { runId: string }) {
  const [data, setData] = useState<unknown>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.debug.context(runId).then(setData, (e: Error) => setErr(e.message));
  }, [runId]);
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return <span className="muted">Loading…</span>;
  return <pre className="json">{JSON.stringify(data, null, 2)}</pre>;
}

// ---- one turn -------------------------------------------------------------------------------------

export function TurnCard({
  turn,
  names,
  selfId,
  dev,
  answerable = true,
  rolling = false,
  onAnswer,
  onRoll,
}: {
  turn: FeedTurn;
  names: Map<string, string>;
  selfId?: string | null;
  dev: boolean;
  answerable?: boolean;
  rolling?: boolean;
  onAnswer: (answer: string) => void;
  onRoll?: (decision: "roll" | "reconsider", auto?: boolean) => void;
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
  const traceId = r?.turn_id ?? turn.turnId ?? turn.live.turnId;
  const devNotes = (r as (PlayResult & { dev_notes?: string[] }) | undefined)?.dev_notes ?? [];
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
        <Mechanics result={r} dev={dev} fresh={turn.live.sentAt > 0} />
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

      {r?.roll_request &&
        (answerable && onRoll ? (
          <RollRequestCard
            request={r.roll_request}
            busy={false}
            rolling={rolling}
            onRoll={() => onRoll("roll")}
            onReconsider={() => onRoll("reconsider")}
            onAutoRoll={() => onRoll("roll", true)}
          />
        ) : (
          <div className="muted small">{r.roll_request.prompt}</div>
        ))}

      {narration && (
        <div className="narration">
          {narration}
          {turn.status === "streaming" && <span className="cursor" />}
        </div>
      )}
      {(turn.status === "streaming" || (dev && turn.live.calls.length > 0 && turn.status !== "done")) && (
        <LiveStatus turn={turn} dev={dev} />
      )}

      {turn.status === "clarify" && turn.clarification &&
        (answerable ? (
          <Clarify c={turn.clarification} onAnswer={onAnswer} />
        ) : (
          <div className="muted small">Asked: {turn.clarification.question}</div>
        ))}
      {turn.status === "error" && <div className="error-box">{turn.error}</div>}

      {dev && devNotes.length > 0 && (
        <div className="mechanics dev-notes">
          {devNotes.map((n, i) => (
            <span key={i} className="mono">
              {n.length > 300 ? `${n.slice(0, 300)}…` : n}
            </span>
          ))}
        </div>
      )}
      {dev && traceId && turn.status !== "streaming" && (
        <div className="turn-meta">
          {r && (
            <>
              <span className="chip dev">{((r.metrics.wall_ms_total ?? 0) / 1000).toFixed(1)} s</span>
              <span className="chip dev">{r.metrics.sync_model_calls ?? 0} calls</span>
              {(r.metrics.degradation_steps ?? []).map((d) => (
                <span className="chip warn" key={d}>
                  {d}
                </span>
              ))}
            </>
          )}
          <button type="button" className="btn small dev" onClick={() => setTraceOpen((o) => !o)}>
            {traceOpen ? "Hide trace" : "Trace"}
          </button>
        </div>
      )}
      {dev && traceId && traceOpen && <TraceView turnId={traceId} />}
    </article>
  );
}

function Mechanics({ result, dev, fresh }: { result: PlayResult; dev: boolean; fresh: boolean }) {
  const lines: JSX.Element[] = [];
  result.actions.forEach((a, i) => {
    const failed = a.status === "invalid" || a.status === "failed";
    lines.push(
      <span key={`a${i}`} className={failed ? "muted" : undefined}>
        ⚙ {a.action.replace(/^(action|social)\./, "").replace(/_/g, " ")}
        {a.target ? ` · ${a.target}` : ""} → {a.status}
        {dev && a.summary ? ` · ${a.summary}` : ""}
      </span>,
    );
  });
  const dice = result.visible_rolls.map((r, i) => <DiceRoll key={`r${i}`} roll={r} dev={dev} fresh={fresh} />);
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
  if (!lines.length && !dice.length) return null;
  return (
    <>
      {dice.length > 0 && <div className="dice-tray">{dice}</div>}
      {lines.length > 0 && <div className="mechanics">{lines}</div>}
    </>
  );
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
  partyIds,
  onSend,
}: {
  busy: boolean;
  others: Participant[];
  partyIds: string[];
  onSend: (text: string, channel: Channel, targets: Participant[]) => void | Promise<void>;
}) {
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<Channel>("auto");
  const [picked, setPicked] = useState<string[]>([]);
  const ref = useRef<HTMLTextAreaElement>(null);
  const present = others.filter((o) => o.actor_id);
  const targets = present.filter((o) => picked.includes(o.actor_id as string));
  const partyHere = present.filter((o) => partyIds.includes(o.actor_id as string));
  const allParty = partyHere.length > 0 && partyHere.every((p) => picked.includes(p.actor_id as string));
  // whispers need someone to whisper to; speech may name who it is for (heard by all)
  const needsTarget = channel === "whisper" && targets.length === 0;
  const picking = channel === "whisper" || channel === "say";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);
  // someone who left the scene cannot stay picked
  useEffect(() => {
    setPicked((p) => p.filter((id) => present.some((o) => o.actor_id === id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [others]);

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const toggleParty = () =>
    setPicked((p) =>
      allParty
        ? p.filter((id) => !partyIds.includes(id))
        : [...new Set([...p, ...partyHere.map((x) => x.actor_id as string)])],
    );

  const submit = () => {
    const t = text.trim();
    if (!t || busy || needsTarget) return;
    void onSend(t, channel, picking ? targets : []);
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };
  const hint =
    channel === "say" && targets.length
      ? `Said aloud to ${targets.map((t) => t.known_as).join(", ")} (everyone present hears)`
      : channel === "whisper" && targets.length
        ? `Only ${targets.map((t) => t.known_as).join(", ")} will hear`
        : CHANNELS.find((c) => c.id === channel)?.hint ?? "";
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
              onClick={() => {
                if (c.id !== channel) setPicked([]); // listeners belong to one way of speaking
                setChannel(c.id);
              }}
              title={c.hint}
            >
              {c.label}
            </button>
          ))}
        </div>
        {picking && present.length > 0 && (
          <div
            className="channels listeners"
            role="group"
            aria-label={channel === "whisper" ? "Whisper to" : "Speak to"}
          >
            <span className="muted small">{channel === "whisper" ? "Whisper to" : "To"}</span>
            {partyHere.length > 1 && (
              <button type="button" aria-pressed={allParty} onClick={toggleParty}>
                Party
              </button>
            )}
            {present.map((o) => (
              <button
                key={o.actor_id}
                type="button"
                aria-pressed={picked.includes(o.actor_id as string)}
                onClick={() => toggle(o.actor_id as string)}
              >
                {o.known_as}
              </button>
            ))}
          </div>
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
