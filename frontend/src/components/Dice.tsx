// Dice on the table (play session 2026-10-05): the check the game calls for, the roll itself,
// and dev proof that the number came from the engine's dice service, not from a model.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RollRequest, VisibleRoll } from "../api/types";
import { readPref, writePref } from "../state";

export const DIE_STYLES = [
  { id: "ivory", label: "Ivory" },
  { id: "obsidian", label: "Obsidian" },
  { id: "crimson", label: "Crimson" },
  { id: "jade", label: "Jade" },
  { id: "gold", label: "Gold" },
  { id: "arcane", label: "Arcane" },
] as const;
export type DieStyle = (typeof DIE_STYLES)[number]["id"];

export function useDieStyle(): [DieStyle, (s: DieStyle) => void] {
  const [style, setStyle] = useState<DieStyle>(() => readPref<DieStyle>("die-style", "ivory"));
  return [
    style,
    (s) => {
      setStyle(s);
      writePref("die-style", s);
    },
  ];
}

const reduceMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A d20 face. `value` null shows a blank face; `tumbling` cycles random faces. */
export function D20({
  value,
  tumbling = false,
  style,
  size = 56,
  outcome,
}: {
  value: number | null;
  tumbling?: boolean;
  style: DieStyle;
  size?: number;
  outcome?: "success" | "failure" | "crit" | "fumble" | null;
}) {
  const [shown, setShown] = useState<number | null>(value);
  useEffect(() => {
    if (!tumbling || reduceMotion()) {
      setShown(value);
      return;
    }
    const id = window.setInterval(() => setShown(1 + Math.floor(Math.random() * 20)), 70);
    return () => window.clearInterval(id);
  }, [tumbling, value]);
  return (
    <svg
      className={`d20 die-${style} ${tumbling ? "tumbling" : "landed"} ${outcome ? `o-${outcome}` : ""}`}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={tumbling ? "rolling a d20" : shown != null ? `d20 shows ${shown}` : "d20"}
    >
      <polygon className="d20-body" points="50,3 93,27 93,73 50,97 7,73 7,27" />
      <polygon className="d20-face" points="50,20 80,70 20,70" />
      <line className="d20-edge" x1="50" y1="3" x2="50" y2="20" />
      <line className="d20-edge" x1="93" y1="27" x2="80" y2="70" />
      <line className="d20-edge" x1="7" y1="27" x2="20" y2="70" />
      <line className="d20-edge" x1="93" y1="73" x2="80" y2="70" />
      <line className="d20-edge" x1="7" y1="73" x2="20" y2="70" />
      <line className="d20-edge" x1="50" y1="97" x2="80" y2="70" />
      <line className="d20-edge" x1="50" y1="97" x2="20" y2="70" />
      <line className="d20-edge" x1="93" y1="27" x2="50" y2="20" />
      <line className="d20-edge" x1="7" y1="27" x2="50" y2="20" />
      <text className="d20-num" x="50" y="58" textAnchor="middle" dominantBaseline="middle">
        {shown ?? ""}
      </text>
    </svg>
  );
}

export function DieStylePicker({ style, onChange }: { style: DieStyle; onChange: (s: DieStyle) => void }) {
  return (
    <div className="die-picker" role="radiogroup" aria-label="Die style">
      {DIE_STYLES.map((d) => (
        <button
          key={d.id}
          type="button"
          role="radio"
          aria-checked={style === d.id}
          title={d.label}
          className={`swatch die-${d.id}`}
          onClick={() => onChange(d.id)}
        >
          <span className="sr-only">{d.label}</span>
        </button>
      ))}
    </div>
  );
}

const sign = (n: number) => (n >= 0 ? `+ ${n}` : `− ${Math.abs(n)}`);

/** The check the game calls for: what is tested, the number to reach, what is at stake. */
export function RollRequestCard({
  request,
  busy,
  rolling,
  onRoll,
  onReconsider,
  onAutoRoll,
}: {
  request: RollRequest;
  busy: boolean;
  rolling: boolean;
  onRoll: () => void;
  onReconsider: () => void;
  onAutoRoll: () => void;
}) {
  const [style, setStyle] = useDieStyle();
  return (
    <section className="roll-request" aria-label="A roll is called for">
      {request.checks.map((c, i) => (
        <div key={i} className="roll-check">
          <D20 value={null} tumbling={rolling} style={style} size={72} />
          <div className="stack" style={{ gap: 6, flex: 1, minWidth: 0 }}>
            <div className="roll-title">
              {c.label} check{c.target_known_as ? ` · ${c.target_known_as}` : ""}
            </div>
            <div className="roll-numbers">
              <span>
                Roll <b>{c.die}</b> {sign(c.bonus)}
              </span>
              <span className="target">
                need <b>{c.dc}</b>
              </span>
            </div>
            <ul className="stakes">
              <li>
                <span className="chip ok">Success</span> {c.stakes.success}
              </li>
              <li>
                <span className="chip bad">Failure</span> {c.stakes.failure}
              </li>
              {c.stakes.retry && (
                <li>
                  <span className="chip">Again?</span> {c.stakes.retry}
                </li>
              )}
            </ul>
          </div>
        </div>
      ))}
      <div className="row roll-actions">
        <button type="button" className="btn primary roll-btn" disabled={busy} onClick={onRoll}>
          {rolling ? "Rolling…" : "Roll"}
        </button>
        <button type="button" className="btn" disabled={busy} onClick={onReconsider}>
          Reconsider
        </button>
        <DieStylePicker style={style} onChange={setStyle} />
        <button type="button" className="btn ghost small" disabled={busy} onClick={onAutoRoll}>
          Auto-roll from now on
        </button>
      </div>
    </section>
  );
}

function outcomeOf(r: VisibleRoll): "success" | "failure" | "crit" | "fumble" | null {
  if (r.natural === 20 && r.expression.includes("d20")) return "crit";
  if (r.natural === 1 && r.expression.includes("d20")) return "fumble";
  if (r.success === true) return "success";
  if (r.success === false) return "failure";
  return null;
}

/** One roll on the table: the die lands, then the arithmetic and the outcome. */
export function DiceRoll({ roll, dev, fresh }: { roll: VisibleRoll; dev: boolean; fresh: boolean }) {
  const [style] = useDieStyle();
  const [tumbling, setTumbling] = useState(fresh && !reduceMotion());
  const [cert, setCert] = useState(false);
  const done = useRef(false);
  useEffect(() => {
    if (!tumbling || done.current) return;
    const id = window.setTimeout(() => {
      done.current = true;
      setTumbling(false);
    }, 1100);
    return () => window.clearTimeout(id);
  }, [tumbling]);
  const outcome = outcomeOf(roll);
  const label = roll.purpose.replace(/^action\./, "").replace(/_/g, " ");
  return (
    <div className={`dice-roll ${tumbling ? "is-rolling" : ""}`} data-testid="dice-roll">
      <D20 value={roll.natural ?? null} tumbling={tumbling} style={style} size={48} outcome={tumbling ? null : outcome} />
      <div className="stack" style={{ gap: 2, minWidth: 0 }}>
        <span className="roll-title">{label.charAt(0).toUpperCase() + label.slice(1)}</span>
        {!tumbling && (
          <span className="roll-math">
            {roll.natural ?? roll.expression} {roll.total - (roll.natural ?? 0) !== 0 && roll.natural != null ? sign(roll.total - roll.natural) : ""} ={" "}
            <b>{roll.total}</b>
            {roll.dc != null && <> vs {roll.dc}</>}
            {outcome && (
              <span className={`chip ${outcome === "success" || outcome === "crit" ? "ok" : "bad"}`} style={{ marginLeft: 8 }}>
                {outcome === "crit" ? "Natural 20" : outcome === "fumble" ? "Natural 1" : outcome === "success" ? "Success" : "Failure"}
                {roll.degree && !["success", "failure"].includes(roll.degree) ? ` · ${roll.degree.replace(/_/g, " ")}` : ""}
              </span>
            )}
          </span>
        )}
        {dev && roll.id && (
          <button type="button" className="chip dev cert-chip" onClick={() => setCert((c) => !c)}>
            engine dice · {roll.id.slice(0, 8)}
          </button>
        )}
        {dev && cert && roll.id && <RollCertificate id={roll.id} />}
      </div>
    </div>
  );
}

function RollCertificate({ id }: { id: string }) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.debug.roll(id).then(setData, (e: Error) => setErr(e.message));
  }, [id]);
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return <span className="muted small">Checking…</span>;
  const roll = data.roll as Record<string, unknown>;
  const replay = data.replay as { ok: boolean; raw: number[] };
  const event = data.event as { seq: number; type: string } | null;
  return (
    <div className="trace small" data-testid="roll-certificate">
      <span className="label">Roll certificate · dev only</span>
      <div>
        {replay.ok ? "✓" : "✗"} Rolled by the engine's dice service, not a model. Replaying seed{" "}
        <span className="mono">{String(roll.seed)}</span> through the engine gives{" "}
        <span className="mono">{JSON.stringify(replay.raw)}</span>
        {replay.ok ? ", the same dice." : ", which does NOT match."}
      </div>
      <div className="mono">
        {String(roll.expression)} · raw {JSON.stringify(roll.raw)} · total {String(roll.total)}
        {event ? ` · event #${event.seq} ${event.type}` : ""}
      </div>
    </div>
  );
}
