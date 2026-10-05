// Developer trace of one turn (GET /debug/turns/{id}). Omniscient: shown only in dev view, always
// in the --dev hue, never mixed into the fiction.
import { useState } from "react";
import { api } from "../api/client";
import type { TurnTrace } from "../api/types";
import { useLoad } from "../state";

export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

const ms = (v: unknown) => (typeof v === "number" ? `${(v / 1000).toFixed(1)} s` : "—");

export function TraceView({ turnId }: { turnId: string }) {
  const { data, error, loading } = useLoad<TurnTrace>(() => api.debug.turn(turnId), [turnId]);
  const [tab, setTab] = useState<"summary" | "resolution" | "rolls" | "events" | "models" | "raw">(
    "summary",
  );
  if (loading && !data) return <div className="trace">Loading trace…</div>;
  if (error) return <div className="trace error-box">{error}</div>;
  if (!data) return null;
  const m = data.metrics ?? {};
  return (
    <div className="trace" data-testid="trace">
      <span className="label">Turn trace · dev only</span>
      <div className="tabs dev-tabs" role="tablist">
        {(
          [
            ["summary", "Summary"],
            ["resolution", `Resolution (${data.resolution.length})`],
            ["rolls", `Rolls (${data.rolls.length})`],
            ["events", `Events (${data.events.length})`],
            ["models", `Model calls (${data.model_runs.length})`],
            ["raw", "Raw"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "summary" && (
        <div className="stack">
          <div className="row">
            <span className="chip dev">wall {ms(m.wall_ms_total)}</span>
            <span className="chip dev">first output {ms(m.ms_to_first_output)}</span>
            <span className="chip dev">narration {ms(m.ms_to_first_narration_token)}</span>
            <span className="chip dev">
              calls {m.sync_model_calls ?? 0}+{m.background_model_calls ?? 0} bg
            </span>
            {(m.degradation_steps ?? []).map((d) => (
              <span key={d} className="chip warn">
                {d}
              </span>
            ))}
          </div>
          {data.actions.length > 0 && (
            <div className="table-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Status</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {data.actions.map((a) => (
                    <tr key={String(a.id)}>
                      <td className="mono">{String(a.action)}</td>
                      <td>{String(a.target ?? "")}</td>
                      <td>{String(a.status)}</td>
                      <td>{String(a.reason ?? "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.messages.length > 0 && (
            <div className="stack">
              {data.messages.map((x, i) => (
                <div key={i} className="small">
                  <span className="chip">{x.channel}</span> <span className="muted">{x.source}</span>{" "}
                  {x.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {tab === "resolution" &&
        (data.resolution.length ? (
          data.resolution.map((r, i) => (
            <details key={i} open={i === 0}>
              <summary>{String(r.summary || r.action_id)}</summary>
              <Json value={r} />
            </details>
          ))
        ) : (
          <span className="muted">No rules resolution this turn.</span>
        ))}
      {tab === "rolls" &&
        (data.rolls.length ? (
          <div className="stack">
            {data.rolls.map((r) => (
              <div key={r.id} className="row mono">
                <span>{r.purpose}</span>
                <span>
                  {r.expression} → <b>{r.total}</b>
                </span>
                {r.hidden_in_production && <span className="chip dev">hidden in play</span>}
              </div>
            ))}
          </div>
        ) : (
          <span className="muted">No rolls.</span>
        ))}
      {tab === "events" && (
        <div className="stack">
          {data.events.map((e) => (
            <details key={e.id}>
              <summary className="event-row">
                <span>#{e.seq}</span>
                <span>{e.type}</span>
              </summary>
              <Json value={e.payload} />
            </details>
          ))}
          {!data.events.length && <span className="muted">No events.</span>}
        </div>
      )}
      {tab === "models" && (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Role</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Tokens</th>
                <th>Context</th>
              </tr>
            </thead>
            <tbody>
              {data.model_runs.map((r) => (
                <ModelRunRow key={r.id} run={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === "raw" && <Json value={data} />}
    </div>
  );
}

function ModelRunRow({ run }: { run: TurnTrace["model_runs"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td className="mono">{run.role}</td>
        <td>{run.status}</td>
        <td>{ms(run.latency_ms)}</td>
        <td className="mono">
          {run.prompt_tokens ?? "?"}+{run.completion_tokens ?? "?"}
        </td>
        <td>
          <button type="button" className="btn small dev" onClick={() => setOpen((o) => !o)}>
            {open ? "Hide" : "Context"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5}>
            <ContextView runId={run.id} />
          </td>
        </tr>
      )}
    </>
  );
}

function ContextView({ runId }: { runId: string }) {
  const { data, error } = useLoad(() => api.debug.context(runId), [runId]);
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <span className="muted">Loading…</span>;
  return <Json value={data} />;
}
