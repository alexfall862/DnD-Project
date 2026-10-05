import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api/client";
import type { CampaignDetail, Uuid } from "./api/types";

// ---- tiny hash router: #/c/<campaign>/<view>[?actor=<id>] -----------------------------------

export type View =
  | "play"
  | "character"
  | "party"
  | "journal"
  | "encyclopedia"
  | "world"
  | "settings"
  | "debug";

export const VIEWS: View[] = [
  "play",
  "character",
  "party",
  "journal",
  "encyclopedia",
  "world",
  "settings",
  "debug",
];

export interface Route {
  campaignId: Uuid | null;
  view: View;
  actorId: Uuid | null;
}

export function parseHash(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  if (parts[0] !== "c" || !parts[1]) return { campaignId: null, view: "play", actorId: null };
  const view = (VIEWS as string[]).includes(parts[2] ?? "") ? (parts[2] as View) : "play";
  return { campaignId: parts[1], view, actorId: params.get("actor") };
}

export function toHash(r: Route): string {
  if (!r.campaignId) return "#/";
  return `#/c/${r.campaignId}/${r.view}${r.actorId ? `?actor=${r.actorId}` : ""}`;
}

function useRoute(): [Route, (r: Partial<Route>) => void] {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback(
    (r: Partial<Route>) => {
      const next = { ...parseHash(window.location.hash), ...r };
      window.location.hash = toHash(next);
    },
    [],
  );
  return [route, go];
}

// ---- per-browser preferences (localStorage; never authoritative) ---------------------------------

export function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode or blocked storage: preferences simply do not persist */
  }
}

// ---- app context ---------------------------------------------------------------------------------

interface AppState {
  route: Route;
  go: (r: Partial<Route>) => void;
  campaign: CampaignDetail | null;
  campaignError: string | null;
  focusActorId: Uuid | null;
  focusName: string | null;
  /** Dev visibility: only possible when the server runs with DEBUG_MODE; toggled per browser. */
  devAvailable: boolean;
  dev: boolean;
  setDev: (on: boolean) => void;
  /** Bumped after every turn so panels re-read authoritative state. */
  version: number;
  bump: () => void;
  reloadCampaign: () => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [route, go] = useRoute();
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [devPref, setDevPref] = useState<boolean>(() => readPref("dev-view", false));
  const [version, setVersion] = useState(0);

  const reloadCampaign = useCallback(async () => {
    if (!route.campaignId) {
      setCampaign(null);
      return;
    }
    try {
      setCampaign(await api.campaign(route.campaignId));
      setCampaignError(null);
    } catch (e) {
      setCampaign(null);
      setCampaignError((e as Error).message);
    }
  }, [route.campaignId]);

  useEffect(() => {
    void reloadCampaign();
  }, [reloadCampaign, version]);

  const focusActorId = useMemo(() => {
    if (!campaign) return null;
    const ids = campaign.focus_actors.map((a) => a.actor_id);
    if (route.actorId && ids.includes(route.actorId)) return route.actorId;
    return ids[0] ?? null;
  }, [campaign, route.actorId]);

  const focusName = campaign?.focus_actors.find((a) => a.actor_id === focusActorId)?.name ?? null;
  const devAvailable = Boolean(campaign?.debug_mode);
  const dev = devAvailable && devPref;

  const setDev = useCallback((on: boolean) => {
    setDevPref(on);
    writePref("dev-view", on);
  }, []);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  // leaving dev mode while on the debug view returns to play
  useEffect(() => {
    if (!dev && route.view === "debug" && campaign) go({ view: "play" });
  }, [dev, route.view, campaign, go]);

  const value: AppState = {
    route,
    go,
    campaign,
    campaignError,
    focusActorId,
    focusName,
    devAvailable,
    dev,
    setDev,
    version,
    bump,
    reloadCampaign,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}

// ---- data hook ------------------------------------------------------------------------------------

export function useLoad<T>(
  load: (() => Promise<T>) | null,
  deps: unknown[],
): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!load) return;
    let live = true;
    setLoading(true);
    load()
      .then((d) => {
        if (live) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n]);
  return { data, error, loading, reload: () => setN((x) => x + 1) };
}
