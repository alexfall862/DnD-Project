// The only module that talks HTTP. Everything the UI renders comes from these calls; nothing is
// derived by parsing narration (Milestone 10 invariant).

import type {
  Belief,
  CampaignDetail,
  CampaignSummary,
  Clarification,
  DebugActor,
  EncyclopediaEntry,
  FeedEntry,
  Here,
  InventoryItem,
  JournalEntry,
  PartyMember,
  PlayRequestBody,
  PlayResult,
  SceneView,
  Sheet,
  TurnTrace,
  Uuid,
} from "./types";

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const e = body.error ?? body;
    return new ApiError(res.status, e.code ?? "HTTP_ERROR", e.message ?? res.statusText, e.details);
  } catch {
    return new ApiError(res.status, "HTTP_ERROR", res.statusText);
  }
}

const q = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, v);
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  campaigns: () => request<CampaignSummary[]>("/campaigns"),
  campaign: (id: Uuid) => request<CampaignDetail>(`/campaigns/${id}`),
  patchSettings: (id: Uuid, changes: Record<string, unknown>) =>
    request<CampaignDetail>(`/campaigns/${id}/settings`, {
      method: "PATCH",
      body: JSON.stringify({ changes }),
    }),
  scene: (id: Uuid, actor: Uuid) => request<SceneView>(`/campaigns/${id}/scene${q({ actor_id: actor })}`),
  party: (id: Uuid, actor: Uuid) =>
    request<PartyMember[]>(`/campaigns/${id}/party${q({ actor_id: actor })}`),
  sheet: (actor: Uuid) => request<Sheet>(`/characters/${actor}/sheet`),
  here: (actor: Uuid) => request<Here>(`/characters/${actor}/here`),
  inventory: (actor: Uuid) => request<InventoryItem[]>(`/characters/${actor}/inventory`),
  feed: (actor: Uuid, limit = 200) =>
    request<FeedEntry[]>(`/characters/${actor}/feed${q({ limit: String(limit) })}`),
  beliefsOf: (actor: Uuid) => request<Belief[]>(`/characters/${actor}/beliefs`),
  journal: (actor: Uuid) => request<JournalEntry[]>(`/characters/${actor}/journal`),
  encyclopedia: (actor: Uuid) => request<EncyclopediaEntry[]>(`/characters/${actor}/encyclopedia`),

  // debug (omniscient): only called when the server reports debug_mode and dev view is on
  debug: {
    seedDemo: (fixture = "frostbridge") =>
      request<{ campaign_id: Uuid; scene_id: Uuid }>(`/debug/seed-demo${q({ fixture })}`, {
        method: "POST",
      }),
    turn: (turnId: Uuid) => request<TurnTrace>(`/debug/turns/${turnId}`),
    roll: (rollId: Uuid) => request<Record<string, unknown>>(`/debug/rolls/${rollId}`),
    actors: (id: Uuid) => request<DebugActor[]>(`/debug/campaigns/${id}/actors`),
    events: (id: Uuid, limit = 60) =>
      request<Record<string, unknown>[]>(`/debug/campaigns/${id}/events${q({ limit: String(limit) })}`),
    facts: (id: Uuid) => request<Record<string, unknown>[]>(`/debug/campaigns/${id}/facts`),
    perspective: (actor: Uuid) => request<Record<string, unknown>>(`/debug/actors/${actor}/perspective`),
    compare: (id: Uuid, actorIds: Uuid[]) =>
      request<Record<string, unknown>>(
        `/debug/campaigns/${id}/perspectives/compare${q({ actor_ids: actorIds.join(",") })}`,
      ),
    metrics: (id: Uuid) => request<Record<string, unknown>[]>(`/debug/campaigns/${id}/metrics`),
    modelRuns: (id: Uuid) => request<Record<string, unknown>[]>(`/debug/campaigns/${id}/model-runs`),
    context: (runId: Uuid) => request<Record<string, unknown>>(`/debug/model-runs/${runId}/context`),
    jobs: (id: Uuid) => request<Record<string, unknown>[]>(`/debug/campaigns/${id}/jobs`),
    advanceTime: (id: Uuid, seconds: number) =>
      request<Record<string, unknown>>(
        `/debug/campaigns/${id}/advance-time${q({ seconds: String(seconds) })}`,
        { method: "POST" },
      ),
    endScene: (id: Uuid, sceneId: Uuid) =>
      request<Record<string, unknown>>(`/debug/campaigns/${id}/scenes/${sceneId}/end`, {
        method: "POST",
      }),
  },
};

// ---- the turn stream (api-contracts §9a) -------------------------------------------------------

export type StreamEvent =
  | { name: "accepted"; data: { turn_id: Uuid } }
  | { name: "stage"; data: { stage: string; label: string } }
  | { name: "roll_request"; data: Record<string, unknown> }
  | { name: "model_call"; data: Record<string, unknown> & { run_id: string; role: string; phase: "started" | "waiting" | "retry" | "finished" } }
  | { name: "mechanics"; data: Record<string, unknown> }
  | { name: "speaker"; data: { actor: Uuid; text: string } }
  | { name: "reaction"; data: Record<string, unknown> }
  | { name: "narration_delta"; data: { text: string } }
  | { name: "complete"; data: Record<string, unknown> }
  | { name: "result"; data: PlayResult }
  | { name: "error"; data: { code: string; message: string; details?: Record<string, unknown> } };

/** Parse an SSE byte stream into events (exported for tests). */
export async function* parseSse(stream: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let name = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length) continue;
      yield { name, data: JSON.parse(data.join("\n")) } as StreamEvent;
    }
  }
}

export class ClarificationNeeded extends Error {
  constructor(public clarification: Clarification) {
    super(clarification.question);
  }
}

/** One player turn, streamed. `onEvent` sees every event; resolves with the full result. */
export async function playStream(
  campaignId: Uuid,
  body: PlayRequestBody,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<PlayResult> {
  const res = await fetch(`${API}/campaigns/${campaignId}/play`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await toError(res);
  let result: PlayResult | null = null;
  for await (const ev of parseSse(res.body)) {
    onEvent(ev);
    if (ev.name === "result") result = ev.data;
    if (ev.name === "error") {
      if (ev.data.code === "ACTION_NEEDS_CLARIFICATION") {
        // the orchestrator and the API both report it; either shape carries the question
        const d = (ev.data.details ?? ev.data) as unknown as Clarification;
        throw new ClarificationNeeded(d);
      }
      throw new ApiError(0, ev.data.code, ev.data.message, ev.data.details);
    }
  }
  if (!result) throw new ApiError(0, "STREAM_ENDED", "the turn ended without a result");
  return result;
}
