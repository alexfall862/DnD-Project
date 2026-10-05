import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { PartyMember } from "../api/types";
import { useApp, type View } from "../state";
import * as I from "./Icons";

interface NavDef {
  view: View;
  label: string;
  icon: (p: { className?: string }) => JSX.Element;
  dev?: boolean;
}

export const NAV: NavDef[] = [
  { view: "play", label: "Play", icon: I.Feather },
  { view: "character", label: "Character", icon: I.Person },
  { view: "party", label: "Party", icon: I.Group },
  { view: "journal", label: "Journal", icon: I.Book },
  { view: "encyclopedia", label: "Encyclopedia", icon: I.Library },
  { view: "world", label: "World", icon: I.Globe },
  { view: "settings", label: "Settings", icon: I.Gear },
  { view: "debug", label: "Debug", icon: I.Bug, dev: true },
];

// phones get five tabs; the rest sit behind "More"
const PHONE_TABS: View[] = ["play", "character", "party", "journal"];

export function DevSwitch() {
  const { devAvailable, dev, setDev } = useApp();
  if (!devAvailable) return null;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dev}
      className="dev-switch"
      onClick={() => setDev(!dev)}
      title="Developer visibility: traces, hidden rolls, omniscient debug views"
    >
      <span className="knob" />
      DEV
    </button>
  );
}

function TopBar() {
  const { campaign, focusName, go } = useApp();
  return (
    <header className="topbar">
      <button type="button" className="brand" onClick={() => go({ campaignId: null })}>
        <I.Lantern className="mark" />
        <span className="label">Lantern Tables</span>
      </button>
      {campaign && (
        <div className="where">
          <span className="title">{campaign.name}</span>
          <span className="sub">
            {focusName ? `${focusName} · ` : ""}
            {campaign.world_time?.label ?? campaign.status}
          </span>
        </div>
      )}
      <span className="spacer" />
      <DevSwitch />
    </header>
  );
}

function PartyMini() {
  const { campaign, focusActorId, version } = useApp();
  const [members, setMembers] = useState<PartyMember[]>([]);
  useEffect(() => {
    if (!campaign || !focusActorId) return;
    api.party(campaign.id, focusActorId).then(setMembers, () => setMembers([]));
  }, [campaign, focusActorId, version]);
  if (!members.length) return null;
  return (
    <div className="party-mini">
      <h3>Party</h3>
      {members.map((m) => (
        <MemberRow key={m.actor_id} m={m} compact />
      ))}
    </div>
  );
}

export function MemberRow({ m, compact = false }: { m: PartyMember; compact?: boolean }) {
  const initial = m.known_as === "you" ? "You" : m.known_as.slice(0, 1).toUpperCase();
  const status = m.with_you
    ? [m.wound_state, ...m.visible_conditions.map((c) => c.replace("condition.", ""))]
        .filter(Boolean)
        .join(" · ")
    : "away";
  return (
    <div className="member">
      <span className={`avatar ${m.with_you ? "" : "away"}`}>{compact ? initial.slice(0, 1) : initial}</span>
      <div style={{ minWidth: 0 }}>
        <div className="name">{m.known_as === "you" ? "You" : m.known_as}</div>
        <div className={`status wound-${(m.wound_state ?? "").replace(" ", "-")}`}>
          {status}
          {!compact && m.controller !== "human" && <span className="muted"> · companion</span>}
        </div>
      </div>
    </div>
  );
}

function Rail() {
  const { route, go, dev } = useApp();
  return (
    <nav className="rail" aria-label="Views">
      {NAV.filter((n) => !n.dev || dev).map((n) => (
        <button
          key={n.view}
          type="button"
          className={`nav-item ${n.dev ? "dev-only" : ""}`}
          aria-current={route.view === n.view ? "page" : undefined}
          onClick={() => go({ view: n.view })}
          title={n.label}
        >
          <n.icon />
          <span className="label">{n.label}</span>
        </button>
      ))}
      <div className="divider" />
      <PartyMini />
    </nav>
  );
}

function TabBar() {
  const { route, go, dev } = useApp();
  const [moreOpen, setMoreOpen] = useState(false);
  const tabs = NAV.filter((n) => PHONE_TABS.includes(n.view));
  const rest = NAV.filter((n) => !PHONE_TABS.includes(n.view) && (!n.dev || dev));
  const inRest = rest.some((n) => n.view === route.view);
  return (
    <>
      <nav className="tabbar" aria-label="Views">
        {tabs.map((n) => (
          <button
            key={n.view}
            type="button"
            className="tab"
            aria-current={route.view === n.view ? "page" : undefined}
            onClick={() => go({ view: n.view })}
          >
            <n.icon />
            {n.label}
          </button>
        ))}
        <button
          type="button"
          className={`tab ${route.view === "debug" ? "dev-only" : ""}`}
          aria-current={inRest ? "page" : undefined}
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((o) => !o)}
        >
          <I.More />
          More
        </button>
      </nav>
      {moreOpen && (
        <div className="more-sheet" role="dialog" aria-label="More views" onClick={() => setMoreOpen(false)}>
          <div className="more-panel" onClick={(e) => e.stopPropagation()}>
            {rest.map((n) => (
              <button
                key={n.view}
                type="button"
                className={`nav-item ${n.dev ? "dev-only" : ""}`}
                aria-current={route.view === n.view ? "page" : undefined}
                onClick={() => {
                  go({ view: n.view });
                  setMoreOpen(false);
                }}
              >
                <n.icon />
                <span>{n.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function Shell({ children, side }: { children: ReactNode; side?: ReactNode }) {
  return (
    <div className={`shell ${side ? "" : "no-side"}`}>
      <TopBar />
      <Rail />
      <main className="main">{children}</main>
      {side && <aside className="side">{side}</aside>}
      <TabBar />
    </div>
  );
}
