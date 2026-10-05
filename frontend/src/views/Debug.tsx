// Omniscient developer view (api-contracts §18–§20). Reachable only with dev visibility on, which
// itself requires the server's DEBUG_MODE. Everything here is styled as dev material.
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { DebugActor } from "../api/types";
import { Json, TraceView } from "../components/Trace";
import { useApp, useLoad } from "../state";

type Tab = "events" | "facts" | "perspectives" | "turns" | "models" | "jobs" | "controls";

export function DebugView() {
  const { campaign } = useApp();
  const [tab, setTab] = useState<Tab>("turns");
  if (!campaign) return null;
  return (
    <div className="page">
      <div className="page-inner" style={{ maxWidth: 1100 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1>Debug</h1>
          <span className="chip dev">omniscient · not your character's knowledge</span>
        </div>
        <div className="tabs dev-tabs" role="tablist">
          {(
            [
              ["turns", "Turns"],
              ["events", "Events"],
              ["facts", "Facts"],
              ["perspectives", "Perspectives"],
              ["models", "Model calls"],
              ["jobs", "Jobs"],
              ["controls", "Controls"],
            ] as [Tab, string][]
          ).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        {tab === "turns" && <Turns />}
        {tab === "events" && <Events />}
        {tab === "facts" && <Facts />}
        {tab === "perspectives" && <Perspectives />}
        {tab === "models" && <Models />}
        {tab === "jobs" && <Jobs />}
        {tab === "controls" && <Controls />}
      </div>
    </div>
  );
}

function Turns() {
  const { campaign, version } = useApp();
  const m = useLoad(() => api.debug.metrics(campaign!.id), [campaign?.id, version]);
  const [open, setOpen] = useState<string | null>(null);
  if (m.error) return <div className="error-box">{m.error}</div>;
  if (!m.data) return <span className="muted">Loading…</span>;
  if (!m.data.length) return <div className="empty">No turns yet.</div>;
  return (
    <div className="stack">
      {m.data.map((t) => {
        const id = String(t.turn_id);
        return (
          <div key={id} className="card dev stack">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="mono">{id.slice(0, 8)}</span>
              <div className="row">
                <span className="chip dev">{(Number(t.wall_ms_total) / 1000).toFixed(1)} s</span>
                <span className="chip dev">{String(t.sync_model_calls)} calls</span>
                {t.budget_breached ? <span className="chip bad">over budget</span> : null}
                <button className="btn small dev" type="button" onClick={() => setOpen(open === id ? null : id)}>
                  {open === id ? "Hide" : "Trace"}
                </button>
              </div>
            </div>
            {open === id && <TraceView turnId={id} />}
          </div>
        );
      })}
    </div>
  );
}

function Events() {
  const { campaign, version } = useApp();
  const ev = useLoad(() => api.debug.events(campaign!.id, 150), [campaign?.id, version]);
  const [filter, setFilter] = useState("");
  if (ev.error) return <div className="error-box">{ev.error}</div>;
  if (!ev.data) return <span className="muted">Loading…</span>;
  const rows = ev.data.filter((e) => !filter || String(e.type ?? e.event_type).includes(filter));
  return (
    <div className="stack">
      <input type="text" placeholder="Filter by event type…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      {rows.map((e, i) => (
        <details key={String(e.id ?? i)} className="card dev">
          <summary className="event-row">
            <span>#{String(e.seq ?? e.sequence_number ?? "")}</span>
            <span>{String(e.type ?? e.event_type)}</span>
          </summary>
          <Json value={e} />
        </details>
      ))}
    </div>
  );
}

function Facts() {
  const { campaign, version } = useApp();
  const f = useLoad(() => api.debug.facts(campaign!.id), [campaign?.id, version]);
  const [q, setQ] = useState("");
  if (f.error) return <div className="error-box">{f.error}</div>;
  if (!f.data) return <span className="muted">Loading…</span>;
  const rows = f.data.filter((x) => !q || JSON.stringify(x).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="stack">
      <input type="text" placeholder="Search facts…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="table-wrap card dev">
        <table className="grid">
          <thead>
            <tr>
              <th>Fact</th>
              <th>Truth</th>
              <th>Canon</th>
              <th>Sensitivity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x, i) => (
              <tr key={String(x.id ?? i)}>
                <td>{String(x.predicate ?? x.key ?? "")}</td>
                <td>{String(x.truth_status ?? "")}</td>
                <td>{String(x.canon_status ?? "")}</td>
                <td>{String(x.sensitivity ?? "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Perspectives() {
  const { campaign, version } = useApp();
  const actors = useLoad<DebugActor[]>(() => api.debug.actors(campaign!.id), [campaign?.id]);
  const [picked, setPicked] = useState<string[]>([]);
  const ids = useMemo(() => picked, [picked]);
  const cmp = useLoad(
    ids.length ? () => api.debug.compare(campaign!.id, ids) : null,
    [campaign?.id, ids.join(","), version],
  );
  if (actors.error) return <div className="error-box">{actors.error}</div>;
  if (!actors.data) return <span className="muted">Loading…</span>;
  const people = actors.data.filter((a) => a.controller);
  const data = cmp.data as { actors?: Record<string, { name: string; beliefs: Record<string, unknown>[] }> } | null;
  return (
    <div className="stack">
      <p className="muted small">Pick actors to compare what each believes against the objective facts.</p>
      <div className="row">
        {people.map((a) => {
          const on = picked.includes(a.actor_id);
          return (
            <button
              key={a.actor_id}
              type="button"
              className={`btn small ${on ? "dev" : ""}`}
              aria-pressed={on}
              onClick={() => setPicked(on ? picked.filter((x) => x !== a.actor_id) : [...picked, a.actor_id])}
            >
              {a.name} <span className="muted">· {a.controller}</span>
            </button>
          );
        })}
      </div>
      {cmp.error && <div className="error-box">{cmp.error}</div>}
      {data?.actors && (
        <div className="sheet-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          {Object.entries(data.actors).map(([id, a]) => (
            <div key={id} className="card dev stack">
              <h2>{a.name}</h2>
              {a.beliefs.length === 0 && <span className="muted small">No beliefs.</span>}
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {a.beliefs.map((b, i) => (
                  <li key={i}>
                    {String((b.proposition as Record<string, unknown> | undefined)?.predicate ?? b.predicate ?? "")}{" "}
                    <span className="muted">
                      {String(b.belief_type ?? "")} {b.confidence != null ? `${Math.round(Number(b.confidence) * 100)}%` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Models() {
  const { campaign, version } = useApp();
  const runs = useLoad(() => api.debug.modelRuns(campaign!.id), [campaign?.id, version]);
  if (runs.error) return <div className="error-box">{runs.error}</div>;
  if (!runs.data) return <span className="muted">Loading…</span>;
  return (
    <div className="stack">
      {runs.data.map((r, i) => (
        <details key={String(r.id ?? i)} className="card dev">
          <summary className="row">
            <span className="mono">{String(r.role)}</span>
            <span className="chip">{String(r.status)}</span>
            <span className="muted small">{r.latency_ms != null ? `${(Number(r.latency_ms) / 1000).toFixed(1)} s` : ""}</span>
          </summary>
          <Json value={r} />
        </details>
      ))}
    </div>
  );
}

function Jobs() {
  const { campaign, version } = useApp();
  const jobs = useLoad(() => api.debug.jobs(campaign!.id), [campaign?.id, version]);
  if (jobs.error) return <div className="error-box">{jobs.error}</div>;
  if (!jobs.data) return <span className="muted">Loading…</span>;
  return jobs.data.length ? <Json value={jobs.data} /> : <div className="empty">No background jobs.</div>;
}

function Controls() {
  const { campaign, focusActorId, bump } = useApp();
  const [out, setOut] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [hours, setHours] = useState(6);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      setOut(await fn());
      bump();
    } catch (e) {
      setOut({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack">
      <div className="card dev stack">
        <h3>Advance time</h3>
        <div className="row">
          <input
            type="number"
            min={1}
            value={hours}
            onChange={(e) => setHours(Math.max(1, Number(e.target.value)))}
            style={{ width: 110 }}
            aria-label="Hours"
          />
          <span>hours</span>
          <button className="btn dev" disabled={busy} onClick={() => run(() => api.debug.advanceTime(campaign!.id, hours * 3600))}>
            Advance and simulate
          </button>
        </div>
      </div>
      <div className="card dev stack">
        <h3>Scene</h3>
        <button
          className="btn dev"
          disabled={busy || !focusActorId}
          onClick={() =>
            run(async () => {
              const scene = await api.scene(campaign!.id, focusActorId!);
              return api.debug.endScene(campaign!.id, scene.scene_id);
            })
          }
        >
          End scene (memory checkpoint + journal)
        </button>
      </div>
      {out !== null && <Json value={out} />}
    </div>
  );
}
