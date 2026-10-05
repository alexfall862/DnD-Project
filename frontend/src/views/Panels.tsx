import { useState } from "react";
import { api } from "../api/client";
import type { Belief, EncyclopediaEntry, InventoryItem, JournalEntry, PartyMember, Sheet } from "../api/types";
import { MemberRow } from "../components/Shell";
import { Json } from "../components/Trace";
import { useApp, useLoad } from "../state";

function Loading({ error }: { error: string | null }) {
  return error ? <div className="error-box">{error}</div> : <div className="muted">Loading…</div>;
}

const clean = (k: string) => k.replace(/^(condition|resource|skill|attr|trait|item)\./, "").replace(/_/g, " ");

// ---- character ------------------------------------------------------------------------------------

export function ResourceBars({ sheet }: { sheet: Sheet }) {
  return (
    <div className="stack">
      {sheet.resources.map((r) =>
        r.tracked_as === "count" ? (
          <div key={r.key} className="row" style={{ justifyContent: "space-between" }}>
            <span className="small">{r.name}</span>
            <span className="small mono">{r.current}</span>
          </div>
        ) : (
        <div key={r.key}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span className="small">{r.name}</span>
            <span className="small mono">
              {r.current}/{r.max}
            </span>
          </div>
          <div className="bar" role="meter" aria-valuemin={0} aria-valuemax={r.max} aria-valuenow={r.current} aria-label={r.name}>
            <span style={{ width: `${r.max ? Math.max(0, Math.min(100, (100 * r.current) / r.max)) : 0}%` }} />
          </div>
        </div>
        ),
      )}
    </div>
  );
}

function Inventory({ items }: { items: InventoryItem[] }) {
  if (!items.length) return <p className="muted small">Carrying nothing of note.</p>;
  return (
    <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {items.map((i) => (
        <li key={i.item_id} className="row" style={{ justifyContent: "space-between" }}>
          <span>{i.name ?? clean(i.template_key ?? "something")}</span>
          {i.equipped && <span className="chip ok">equipped</span>}
        </li>
      ))}
    </ul>
  );
}

export function CharacterView() {
  const { focusActorId, version } = useApp();
  const sheet = useLoad<Sheet>(focusActorId ? () => api.sheet(focusActorId) : null, [focusActorId, version]);
  const inv = useLoad<InventoryItem[]>(focusActorId ? () => api.inventory(focusActorId) : null, [focusActorId, version]);
  if (!sheet.data) return <div className="page"><div className="page-inner"><Loading error={sheet.error} /></div></div>;
  const s = sheet.data;
  return (
    <div className="page">
      <div className="page-inner">
        <h1>{s.name}</h1>
        <section className="card stack">
          <h3>Condition</h3>
          <ResourceBars sheet={s} />
          <div className="row">
            {s.conditions.length ? (
              s.conditions.map((c) => (
                <span key={c.key} className="chip warn">
                  {c.name}
                  {c.intensity > 1 ? ` ×${c.intensity}` : ""}
                </span>
              ))
            ) : (
              <span className="muted small">No conditions.</span>
            )}
          </div>
        </section>
        <section className="card stack">
          <h3>Attributes</h3>
          <div className="sheet-grid">
            {s.attributes.map((a) => (
              <div key={a.key} className="stat" title={a.description}>
                <span className="v">{a.value}</span>
                <span className="k">{a.name}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="card stack">
          <h3>Skills</h3>
          {s.skills.length ? (
            <dl className="kv">
              {s.skills.map((k) => (
                <div key={k.key} style={{ display: "contents" }}>
                  <dt title={k.description}>{k.name}</dt>
                  <dd>{k.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <span className="muted small">Untrained.</span>
          )}
        </section>
        {s.traits.length > 0 && (
          <section className="card stack">
            <h3>Traits</h3>
            {s.traits.map((t) => (
              <div key={t.key}>
                <strong>{t.name}</strong>
                {t.description && <div className="muted small">{t.description}</div>}
              </div>
            ))}
          </section>
        )}
        <section className="card stack">
          <h3>Inventory</h3>
          {inv.data ? <Inventory items={inv.data} /> : <Loading error={inv.error} />}
        </section>
      </div>
    </div>
  );
}

/** Desktop right-hand panel: the essentials while playing. */
export function SidePanel() {
  const { campaign, focusActorId, version, dev } = useApp();
  const sheet = useLoad<Sheet>(focusActorId ? () => api.sheet(focusActorId) : null, [focusActorId, version]);
  const inv = useLoad<InventoryItem[]>(focusActorId ? () => api.inventory(focusActorId) : null, [focusActorId, version]);
  const party = useLoad<PartyMember[]>(
    campaign && focusActorId ? () => api.party(campaign.id, focusActorId) : null,
    [campaign?.id, focusActorId, version],
  );
  return (
    <>
      <section>
        <h3>{sheet.data?.name ?? "You"}</h3>
        {sheet.data ? <ResourceBars sheet={sheet.data} /> : <Loading error={sheet.error} />}
        {sheet.data && sheet.data.conditions.length > 0 && (
          <div className="row" style={{ marginTop: 8 }}>
            {sheet.data.conditions.map((c) => (
              <span key={c.key} className="chip warn">
                {c.name}
              </span>
            ))}
          </div>
        )}
      </section>
      <section>
        <h3>Party</h3>
        {(party.data ?? []).map((m) => (
          <MemberRow key={m.actor_id} m={m} />
        ))}
      </section>
      <section>
        <h3>Carrying</h3>
        {inv.data ? <Inventory items={inv.data} /> : <Loading error={inv.error} />}
      </section>
      {dev && campaign && (
        <section className="card dev small">
          <h3 style={{ color: "var(--dev)" }}>Dev</h3>
          <div className="mono">world v{campaign.world_version}</div>
          <div className="mono">tick {campaign.world_time?.tick ?? "—"}</div>
          <div className="mono" style={{ wordBreak: "break-all" }}>
            actor {focusActorId}
          </div>
        </section>
      )}
    </>
  );
}

// ---- party ----------------------------------------------------------------------------------------

export function PartyView() {
  const { campaign, focusActorId, version } = useApp();
  const party = useLoad<PartyMember[]>(
    campaign && focusActorId ? () => api.party(campaign.id, focusActorId) : null,
    [campaign?.id, focusActorId, version],
  );
  return (
    <div className="page">
      <div className="page-inner">
        <h1>Party</h1>
        <p className="muted small">
          What you can see of your companions. Someone who is elsewhere is simply away: you learn how
          they fared when you meet again or are told.
        </p>
        {party.data ? (
          <div className="card">
            {party.data.map((m) => (
              <MemberRow key={m.actor_id} m={m} />
            ))}
          </div>
        ) : (
          <Loading error={party.error} />
        )}
      </div>
    </div>
  );
}

// ---- journal & encyclopedia ----------------------------------------------------------------------

export function JournalView() {
  const { focusActorId, version } = useApp();
  const j = useLoad<JournalEntry[]>(focusActorId ? () => api.journal(focusActorId) : null, [focusActorId, version]);
  return (
    <div className="page">
      <div className="page-inner">
        <h1>Journal</h1>
        {!j.data ? (
          <Loading error={j.error} />
        ) : j.data.length === 0 ? (
          <div className="empty">Nothing written yet. Entries appear when a scene ends.</div>
        ) : (
          [...j.data].reverse().map((e) => (
            <article key={e.id} className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2>{e.title}</h2>
                <span className="chip">{e.entry_type}</span>
              </div>
              <div className="narration" style={{ fontSize: "1rem" }}>
                {e.body}
              </div>
            </article>
          ))
        )}
      </div>
    </div>
  );
}

export function EncyclopediaView() {
  const { focusActorId, version, dev } = useApp();
  const enc = useLoad<EncyclopediaEntry[]>(
    focusActorId ? () => api.encyclopedia(focusActorId) : null,
    [focusActorId, version],
  );
  const [cat, setCat] = useState<string>("all");
  const [open, setOpen] = useState<string | null>(null);
  const cats = Array.from(new Set((enc.data ?? []).map((e) => e.category))).sort();
  const shown = (enc.data ?? []).filter((e) => cat === "all" || e.category === cat);
  return (
    <div className="page">
      <div className="page-inner">
        <h1>Encyclopedia</h1>
        <p className="muted small">Everything here is what you know or suspect, not necessarily what is true.</p>
        <div className="segmented" role="group" aria-label="Category">
          {["all", ...cats].map((c) => (
            <button key={c} type="button" aria-pressed={cat === c} onClick={() => setCat(c)}>
              {c}
            </button>
          ))}
        </div>
        {!enc.data ? (
          <Loading error={enc.error} />
        ) : shown.length === 0 ? (
          <div className="empty">Nothing known yet.</div>
        ) : (
          shown.map((e) => (
            <article key={e.entity_id} className="card stack">
              <button
                type="button"
                className="row"
                style={{ justifyContent: "space-between", background: "none", border: 0, padding: 0, cursor: "pointer", textAlign: "left" }}
                aria-expanded={open === e.entity_id}
                onClick={() => setOpen(open === e.entity_id ? null : e.entity_id)}
              >
                <h2>{e.display_name}</h2>
                <span className="chip">{e.category}</span>
              </button>
              {e.summary && <p style={{ margin: 0 }}>{e.summary}</p>}
              {open === e.entity_id && <KnowledgeList k={e.knowledge} raw={dev} />}
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function KnowledgeList({ k, raw }: { k: Record<string, unknown>; raw: boolean }) {
  const groups = Object.entries(k).filter(([, v]) => Array.isArray(v) && (v as unknown[]).length);
  return (
    <div className="stack small">
      {groups.map(([name, items]) => (
        <div key={name}>
          <h3>{name.replace(/_/g, " ")}</h3>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {(items as unknown[]).map((it, i) => (
              <li key={i}>{typeof it === "string" ? it : String((it as Record<string, unknown>).text ?? (it as Record<string, unknown>).predicate ?? JSON.stringify(it))}</li>
            ))}
          </ul>
        </div>
      ))}
      {raw && <Json value={k} />}
    </div>
  );
}

// ---- world ----------------------------------------------------------------------------------------

export function WorldView() {
  const { campaign, focusActorId, version } = useApp();
  const scene = useLoad(
    campaign && focusActorId ? () => api.scene(campaign.id, focusActorId) : null,
    [campaign?.id, focusActorId, version],
  );
  const beliefs = useLoad<Belief[]>(
    focusActorId ? () => api.beliefsOf(focusActorId) : null,
    [focusActorId, version],
  );
  return (
    <div className="page">
      <div className="page-inner">
        <h1>World</h1>
        <section className="card stack">
          <h3>Where you are</h3>
          {scene.data ? (
            <>
              <h2>{scene.data.location_known_as ?? "Somewhere unfamiliar"}</h2>
              <div className="muted small">
                {campaign?.world_time?.label} · {scene.data.scene_type}
                {scene.data.your_zone ? ` · ${scene.data.your_zone}` : ""}
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {scene.data.participants
                  .filter((p) => !p.is_self)
                  .map((p) => (
                    <li key={p.entity_id}>
                      {p.known_as}
                      {p.zone ? <span className="muted"> · {p.zone}</span> : null}
                      {p.visible_conditions.map((c) => (
                        <span key={c} className="chip warn" style={{ marginLeft: 6 }}>
                          {clean(c)}
                        </span>
                      ))}
                    </li>
                  ))}
              </ul>
            </>
          ) : (
            <Loading error={scene.error} />
          )}
        </section>
        <section className="card stack">
          <h3>What you believe</h3>
          {!beliefs.data ? (
            <Loading error={beliefs.error} />
          ) : beliefs.data.length === 0 ? (
            <span className="muted small">Nothing yet.</span>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18 }} className="stack small">
              {beliefs.data.map((b, i) => (
                <li key={i}>
                  {[b.subject_known_as, String(b.proposition.predicate ?? ""), b.object_known_as ?? (b.proposition.value as string | undefined)]
                    .filter(Boolean)
                    .join(" ")}{" "}
                  <span className="chip">{b.belief_type}</span>{" "}
                  <span className="muted">{Math.round(b.confidence * 100)}%</span>
                  {b.source_known_as && <span className="muted"> · from {b.source_known_as}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
