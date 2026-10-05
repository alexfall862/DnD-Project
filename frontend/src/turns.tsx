// The play feed and the turn in flight, held above the views (play session 2026-10-05:
// switching views unmounted the Play view and the running turn's status vanished until the
// response arrived). One store per campaign + focus actor; the stream keeps running whatever
// view is shown.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, ClarificationNeeded, api, playStream, type StreamEvent } from "./api/client";
import type { Channel, Clarification, FeedEntry, PlayResult, Uuid } from "./api/types";
import { useApp } from "./state";

export interface CallInfo {
  run_id: string;
  role: string;
  phase: "started" | "waiting" | "retry" | "finished";
  status?: string;
  startedAt: number;
  endedAt?: number;
  context_snapshot_id?: string | null;
  context_tokens?: number;
  max_tokens?: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  model?: string;
  notes: string[];
}

export interface LiveState {
  sentAt: number;
  acceptedAt?: number;
  turnId?: string;
  stage?: { stage: string; label: string; at: number };
  stages: { stage: string; label: string; at: number }[];
  calls: CallInfo[];
  speakers: { actor: Uuid; text: string }[];
  narration: string;
  mechanics: string[];
}

export interface FeedTurn {
  key: string;
  input: { text: string; channel: Channel; to: string[] };
  status: "streaming" | "done" | "error" | "clarify";
  live: LiveState;
  result?: PlayResult;
  error?: string;
  clarification?: Clarification;
  turnId?: string;
  endedAt?: number;
}

export interface Target {
  actor_id: string | null;
  known_as: string;
}

const emptyLive = (sentAt = 0): LiveState => ({
  sentAt,
  stages: [],
  calls: [],
  speakers: [],
  narration: "",
  mechanics: [],
});

/** Server history → feed turns, including failed and clarification turns. */
export function fromServer(entries: FeedEntry[]): FeedTurn[] {
  return entries.map((e) => {
    const r = e.result as PlayResult & {
      error?: { code: string; message: string };
      clarification?: Clarification;
    };
    const base = {
      key: e.turn_id,
      turnId: e.turn_id,
      input: e.input,
      live: emptyLive(),
    };
    if (r.error) return { ...base, status: "error" as const, error: `${r.error.code}: ${r.error.message}` };
    if (r.clarification) return { ...base, status: "clarify" as const, clarification: r.clarification };
    return { ...base, status: "done" as const, result: r };
  });
}

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

/** Fold one stream event into the live state (exported for tests). */
export function applyEvent(live: LiveState, e: StreamEvent, now: number): LiveState {
  switch (e.name) {
    case "accepted":
      return { ...live, acceptedAt: now, turnId: e.data.turn_id };
    case "stage": {
      const st = { ...(e.data as { stage: string; label: string }), at: now };
      return { ...live, stage: st, stages: [...live.stages, st] };
    }
    case "model_call": {
      const d = e.data as Record<string, unknown> & { run_id: string; role: string; phase: CallInfo["phase"] };
      const calls = [...live.calls];
      const i = calls.findIndex((c) => c.run_id === d.run_id);
      if (i < 0) {
        calls.push({
          run_id: d.run_id,
          role: d.role,
          phase: d.phase,
          startedAt: now,
          context_snapshot_id: (d.context_snapshot_id as string) ?? null,
          context_tokens: d.context_tokens as number,
          max_tokens: d.max_tokens as number,
          model: d.model as string,
          notes: [],
        });
      } else {
        const c = { ...calls[i], phase: d.phase, notes: [...calls[i].notes] };
        if (d.phase === "waiting") c.notes.push(`waiting: ${String(d.reason)}${d.wait_s ? ` (${d.wait_s}s)` : ""}`);
        if (d.phase === "retry") c.notes.push(`retry: ${String(d.reason)}`);
        if (d.phase === "finished") {
          c.status = d.status as string;
          c.endedAt = now;
          c.prompt_tokens = d.prompt_tokens as number | null;
          c.completion_tokens = d.completion_tokens as number | null;
          if (d.error) c.notes.push(String(d.error));
        }
        calls[i] = c;
      }
      return { ...live, calls };
    }
    case "narration_delta":
      return { ...live, narration: live.narration + e.data.text };
    case "speaker":
      return { ...live, speakers: [...live.speakers, e.data] };
    case "mechanics": {
      const line = mechanicsLine(e.data);
      return line ? { ...live, mechanics: [...live.mechanics, line] } : live;
    }
    default:
      return live;
  }
}

interface TurnsState {
  feed: FeedTurn[];
  feedError: string | null;
  busy: boolean;
  send: (
    text: string,
    channel: Channel,
    targets: Target[],
    clarificationId?: string,
    roll?: { id: string; decision: "roll" | "reconsider" },
    checkSkill?: string,
  ) => Promise<void>;
  /** The composer's unsent text: kept here (and per browser tab) so changing views keeps it
   * (play session 2: a half-written turn was lost on a trip to the encyclopedia). */
  draft: string;
  setDraft: (text: string) => void;
}

const draftKey = (cid: string, actor: string) => `ttrpg.draft.${cid}.${actor}`;

function loadDraft(key: string): string {
  try {
    return window.sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

const Ctx = createContext<TurnsState | null>(null);

export function TurnsProvider({ children }: { children: ReactNode }) {
  const { campaign, focusActorId, bump } = useApp();
  const cid = campaign?.id ?? "";
  const [feed, setFeed] = useState<FeedTurn[]>([]);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const owner = useRef("");
  const [draft, setDraftState] = useState("");
  useEffect(() => {
    if (cid && focusActorId) setDraftState(loadDraft(draftKey(cid, focusActorId)));
  }, [cid, focusActorId]);
  const setDraft = useCallback(
    (text: string) => {
      setDraftState(text);
      if (!cid || !focusActorId) return;
      try {
        if (text) window.sessionStorage.setItem(draftKey(cid, focusActorId), text);
        else window.sessionStorage.removeItem(draftKey(cid, focusActorId));
      } catch {
        // storage unavailable: the draft still lives in memory
      }
    },
    [cid, focusActorId],
  );

  useEffect(() => {
    const key = `${cid}:${focusActorId}`;
    if (!cid || !focusActorId) return;
    if (owner.current !== key) {
      owner.current = key;
      setFeed([]);
    }
    let live = true;
    api.feed(focusActorId).then(
      (entries) => {
        if (!live) return;
        // keep a turn still streaming; the server copy replaces finished ones
        setFeed((f) => [...fromServer(entries), ...f.filter((t) => t.status === "streaming")]);
        setFeedError(null);
      },
      (e: Error) => live && setFeedError(e.message),
    );
    return () => {
      live = false;
    };
  }, [cid, focusActorId]);

  const send = useCallback(
    async (
      text: string,
      channel: Channel,
      targets: Target[],
      clarificationId?: string,
      roll?: { id: string; decision: "roll" | "reconsider" },
      checkSkill?: string,
    ) => {
      if (!cid || !focusActorId) return;
      const key = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const turn: FeedTurn = {
        key,
        input: { text: checkSkill ? `[${checkSkill} check] ${text}` : text, channel, to: targets.map((t) => t.known_as) },
        status: "streaming",
        live: emptyLive(Date.now()),
      };
      setFeed((f) => [...f, turn]);
      setBusy(true);
      const update = (fn: (t: FeedTurn) => FeedTurn) =>
        setFeed((f) => f.map((t) => (t.key === key ? fn(t) : t)));
      try {
        const result = await playStream(
          cid,
          {
            actor_id: focusActorId,
            text,
            channel,
            target_actor_ids: targets.map((t) => t.actor_id).filter((x): x is string => !!x),
            clarification_id: clarificationId,
            roll_request_id: roll?.id,
            roll_decision: roll?.decision,
            check_skill: checkSkill,
          },
          (e) => update((t) => ({ ...t, turnId: t.turnId ?? (e.name === "accepted" ? e.data.turn_id : undefined), live: applyEvent(t.live, e, Date.now()) })),
        );
        update((t) => ({ ...t, status: "done", result, endedAt: Date.now() }));
        bump();
      } catch (err) {
        if (err instanceof ClarificationNeeded) {
          update((t) => ({ ...t, status: "clarify", clarification: err.clarification, endedAt: Date.now() }));
        } else {
          const msg = err instanceof ApiError ? `${err.code}: ${err.message}` : (err as Error).message;
          update((t) => ({ ...t, status: "error", error: msg, endedAt: Date.now() }));
        }
      } finally {
        setBusy(false);
      }
    },
    [cid, focusActorId, bump],
  );

  return <Ctx.Provider value={{ feed, feedError, busy, send, draft, setDraft }}>{children}</Ctx.Provider>;
}

export function useTurns(): TurnsState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTurns outside TurnsProvider");
  return v;
}

/** Re-render every `ms` while `active` (live elapsed timers). */
export function useNow(active: boolean, ms = 500): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [active, ms]);
  return now;
}
