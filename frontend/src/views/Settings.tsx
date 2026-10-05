import { useEffect, useState } from "react";
import { api } from "../api/client";
import { DieStylePicker, useDieStyle } from "../components/Dice";
import { DevSwitch } from "../components/Shell";
import { readPref, useApp, writePref } from "../state";

type Theme = "system" | "light" | "dark";

export function applyTheme(t: Theme) {
  const root = document.documentElement;
  if (t === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
}

export function SettingsView() {
  const { campaign, reloadCampaign, devAvailable } = useApp();
  const [theme, setTheme] = useState<Theme>(() => readPref<Theme>("theme", "system"));
  const [dieStyle, setDieStyle] = useDieStyle();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    applyTheme(theme);
    writePref("theme", theme);
  }, [theme]);

  if (!campaign) return null;
  const s = campaign.settings;
  const save = async (changes: Record<string, unknown>) => {
    setSaving(Object.keys(changes)[0]);
    setError(null);
    try {
      await api.patchSettings(campaign.id, changes);
      await reloadCampaign();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  };
  const spotlight = (s.spotlight as Record<string, unknown> | undefined) ?? {};

  return (
    <div className="page">
      <div className="page-inner">
        <h1>Settings</h1>
        {error && <div className="error-box">{error}</div>}

        <section className="card stack">
          <h3>This device</h3>
          <label className="stack">
            <span>Theme</span>
            <div className="segmented" role="group" aria-label="Theme">
              {(["system", "light", "dark"] as Theme[]).map((t) => (
                <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>
                  {t}
                </button>
              ))}
            </div>
          </label>
          {devAvailable ? (
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div>Developer visibility</div>
                <div className="muted small">
                  Turn traces, hidden rolls, model calls and the omniscient Debug view. Shown in
                  violet; none of it is known to your character.
                </div>
              </div>
              <DevSwitch />
            </div>
          ) : (
            <p className="muted small">
              Developer visibility is unavailable: the server is not running with DEBUG_MODE.
            </p>
          )}
        </section>

        <section className="card stack">
          <h3>Dice</h3>
          <label className="stack">
            <span>When the game calls for a roll</span>
            <div className="segmented" role="group" aria-label="Dice mode">
              {[
                ["manual", "I roll"],
                ["auto", "Auto-roll"],
              ].map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={(s.dice_mode ?? "manual") === v}
                  disabled={saving !== null}
                  onClick={() => save({ dice_mode: v })}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="muted small">
              With "I roll", you see the check, the number to reach and what is at stake, then
              roll yourself. Either way the engine rolls the dice, never the storyteller.
            </span>
          </label>
          <div className="stack">
            <span>Your dice (this device)</span>
            <DieStylePicker style={dieStyle} onChange={setDieStyle} />
          </div>
        </section>

        <section className="card stack">
          <h3>Table (saved with the campaign)</h3>
          <label className="stack">
            <span>Narration style</span>
            <div className="segmented" role="group" aria-label="Narration style">
              {["terse", "standard", "rich"].map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={(s.narration_style ?? "standard") === v}
                  disabled={saving !== null}
                  onClick={() => save({ narration_style: v })}
                >
                  {v}
                </button>
              ))}
            </div>
          </label>
          <label className="stack">
            <span>Companion reactions per turn</span>
            <div className="segmented" role="group" aria-label="Companion reactions">
              {[0, 1, 2].map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={(spotlight.visible_reactions ?? 2) === v}
                  disabled={saving !== null}
                  onClick={() => save({ spotlight: { ...spotlight, visible_reactions: v } })}
                >
                  {v}
                </button>
              ))}
            </div>
            <span className="muted small">Fewer reactions make turns faster.</span>
          </label>
          <label className="stack">
            <span>Watching companions elsewhere (spectator)</span>
            <div className="segmented" role="group" aria-label="Spectator mode">
              {["off", "summary", "full"].map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={(s.spectator_mode ?? "off") === v}
                  disabled={saving !== null}
                  onClick={() => save({ spectator_mode: v })}
                >
                  {v}
                </button>
              ))}
            </div>
            <span className="muted small">
              Out of character only: it never tells your character anything.
            </span>
          </label>
        </section>
      </div>
    </div>
  );
}
