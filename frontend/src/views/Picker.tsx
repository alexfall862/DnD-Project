import { useState } from "react";
import { api } from "../api/client";
import type { CampaignSummary } from "../api/types";
import * as I from "../components/Icons";
import { useApp, useLoad } from "../state";

export function PickerView() {
  const { go } = useApp();
  const list = useLoad<CampaignSummary[]>(() => api.campaigns(), []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const demo = async (fixture: string) => {
    setBusy(true);
    setError(null);
    try {
      const w = await api.debug.seedDemo(fixture);
      go({ campaignId: w.campaign_id, view: "play", actorId: null });
    } catch (e) {
      setError(`${(e as Error).message} (demo campaigns need the server's DEBUG_MODE)`);
    } finally {
      setBusy(false);
    }
  };

  const playable = (list.data ?? []).filter((c) => c.status === "active");
  const other = (list.data ?? []).filter((c) => c.status !== "active");

  return (
    <div className="picker">
      <div className="hero stack" style={{ alignItems: "center" }}>
        <I.Lantern className="mark" />
        <h1>Lantern Tables</h1>
        <p className="muted">Pick up a campaign where you left it, or open the Frostbridge demo.</p>
      </div>
      {error && <div className="error-box" style={{ maxWidth: 640, width: "100%" }}>{error}</div>}
      <div className="list">
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => demo("frostbridge")}>
            New Frostbridge demo
          </button>
          <button className="btn" disabled={busy} onClick={() => demo("tavern")}>
            Red Lantern scene only
          </button>
        </div>
        {list.error && <div className="error-box">{list.error}</div>}
        {list.data && playable.length === 0 && (
          <div className="empty">No campaigns in play yet.</div>
        )}
        {playable.map((c) => (
          <button
            key={c.id}
            type="button"
            className="card campaign-row"
            onClick={() => go({ campaignId: c.id, view: "play", actorId: null })}
          >
            <I.Feather style={{ width: 22, height: 22, color: "var(--accent)" }} />
            <span className="grow">
              <strong>{c.name}</strong>
              <div className="muted small">
                {c.ruleset} · updated {new Date(c.updated_at).toLocaleString()}
              </div>
            </span>
          </button>
        ))}
        {other.length > 0 && (
          <details>
            <summary className="muted small">Drafts and other campaigns ({other.length})</summary>
            <div className="stack" style={{ marginTop: 8 }}>
              {other.map((c) => (
                <div key={c.id} className="card row" style={{ justifyContent: "space-between" }}>
                  <span>{c.name}</span>
                  <span className="chip">{c.status}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
