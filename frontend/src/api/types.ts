// Shapes of the backend's JSON (app/api/v1/*). Normal endpoints are perspective-safe: they
// describe what the focus actor knows. Debug shapes are omniscient and only fetched in dev mode.

export type Uuid = string;

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown>; request_id?: string };
}

export interface CampaignSummary {
  id: Uuid;
  name: string;
  status: string;
  campaign_mode: string;
  ruleset: string;
  updated_at: string;
}

export interface WorldTime {
  tick: number;
  day: number;
  hour: number;
  minute: number;
  label: string;
}

export interface CampaignDetail {
  id: Uuid;
  name: string;
  description: string | null;
  status: string;
  ruleset: string;
  world_version: number;
  world_time: WorldTime | null;
  settings: Record<string, unknown>;
  debug_mode: boolean;
  focus_actors: { actor_id: Uuid; name: string }[];
}

export interface Participant {
  entity_id: Uuid;
  actor_id: Uuid | null;
  known_as: string;
  is_self: boolean;
  visible_conditions: string[];
  zone: string | null;
}

export interface SceneView {
  scene_id: Uuid;
  scene_type: string;
  location_known_as: string | null;
  world_tick: number;
  your_zone: string | null;
  participants: Participant[];
}

export interface InventoryItem {
  item_id: Uuid;
  name: string | null;
  template_key: string | null;
  equipped: boolean;
  properties: Record<string, unknown>;
}

export interface SheetEntry {
  key: string;
  name: string;
  value: number;
  description: string;
}

export interface Sheet {
  actor_id: Uuid;
  name: string;
  attributes: SheetEntry[];
  skills: SheetEntry[];
  traits: SheetEntry[];
  resources: { key: string; name: string; current: number; max: number }[];
  conditions: { key: string; name: string; intensity: number }[];
}

export interface PartyMember {
  actor_id: Uuid;
  known_as: string;
  controller: string;
  is_focus: boolean;
  with_you: boolean;
  wound_state: "unhurt" | "hurt" | "badly hurt" | "down" | null;
  visible_conditions: string[];
}

export interface Belief {
  proposition: Record<string, unknown>;
  belief_type: string;
  confidence: number;
  status: string;
  source_type: string;
  source_known_as: string | null;
  subject_known_as: string | null;
  object_known_as: string | null;
}

export interface JournalEntry {
  id: Uuid;
  entry_type: string;
  title: string;
  body: string;
  game_tick: number;
  from_sequence: number | null;
  to_sequence: number | null;
}

export interface EncyclopediaEntry {
  entity_id: Uuid;
  category: string;
  display_name: string;
  summary: string;
  knowledge: Record<string, unknown>;
}

export type Channel = "auto" | "do" | "say" | "whisper" | "private" | "ooc";

export interface PlayRequestBody {
  actor_id: Uuid;
  text: string;
  channel: Channel;
  target_actor_ids?: Uuid[];
  clarification_id?: Uuid;
  roll_request_id?: Uuid;
  roll_decision?: "roll" | "reconsider";
}

export interface SpeakerLine {
  actor_id: Uuid;
  channel: string;
  text: string;
  recipients?: Uuid[];
}

export interface VisibleRoll {
  id?: string;
  expression: string;
  raw: unknown;
  natural?: number | null;
  modifier: number;
  total: number;
  purpose: string;
  dc?: number | null;
  success?: boolean | null;
  degree?: string | null;
  source?: string;
}

export interface RollCheck {
  label: string;
  kind: string;
  target_known_as: string | null;
  die: string;
  bonus: number;
  dc: number;
  attribute: string | null;
  skill: string | null;
  stakes: { success: string; failure: string; retry?: string };
}

export interface RollRequest {
  id: Uuid;
  checks: RollCheck[];
  prompt: string;
}

export interface ActionResult {
  action: string;
  target?: string | null;
  status: string;
  reason?: string | null;
  summary?: string;
  text?: string;
}

export interface StateChange {
  resource?: string;
  before?: number;
  after?: number;
  [k: string]: unknown;
}

export interface TurnMetricsView {
  sync_model_calls?: number;
  background_model_calls?: number;
  wall_ms_total?: number;
  ms_to_first_output?: number;
  ms_to_first_narration_token?: number;
  calls_by_role?: Record<string, number>;
  degradation_steps?: string[];
  [k: string]: unknown;
}

export interface PlayResult {
  turn_id: Uuid;
  channel: string;
  narration: string | null;
  speakers: SpeakerLine[];
  visible_rolls: VisibleRoll[];
  mechanical_notices: string[];
  state_changes: StateChange[];
  actions: ActionResult[];
  assertions: Record<string, unknown>[];
  time_advanced_seconds: number;
  versions: Record<string, number | null>;
  needs_player_input: boolean;
  metrics: TurnMetricsView;
  ooc: string | null;
  dev_notes?: string[];
  roll_request?: RollRequest | null;
}

export interface Clarification {
  clarification_id: Uuid;
  question: string;
  candidates: { id?: string; known_as?: string; label?: string; [k: string]: unknown }[];
  original_input: string;
  reason?: string | null;
}

/** One turn of the player's server-side feed, exactly as the API returned it then. */
export interface FeedEntry {
  turn_id: Uuid;
  created_at: string;
  input: { text: string; channel: Channel; to: string[] };
  result: PlayResult;
}

// ---- debug (omniscient; dev mode only) -----------------------------------------------------

export interface TurnTrace {
  turn_id: Uuid;
  metrics: TurnMetricsView | null;
  intents: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  resolution: Record<string, unknown>[];
  rolls: (VisibleRoll & { id: Uuid; visibility: string; hidden_in_production: boolean })[];
  messages: { speaker_actor_id: Uuid | null; channel: string; source: string; text: string }[];
  events: { id: Uuid; seq: number; type: string; tick: number; payload: Record<string, unknown> }[];
  model_runs: {
    id: Uuid;
    role: string;
    status: string;
    latency_ms: number | null;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    model_echo: string | null;
    context_snapshot_id: Uuid | null;
  }[];
}

export interface DebugActor {
  actor_id: Uuid;
  entity_id: Uuid;
  name: string;
  controller: string | null;
  importance: string;
  scene_id: Uuid | null;
}
