import { useEffect } from "react";
import { Shell } from "./components/Shell";
import { AppProvider, readPref, useApp } from "./state";
import { TurnsProvider } from "./turns";
import { DebugView } from "./views/Debug";
import {
  CharacterView,
  EncyclopediaView,
  JournalView,
  PartyView,
  SidePanel,
  WorldView,
} from "./views/Panels";
import { PickerView } from "./views/Picker";
import { PlayView } from "./views/Play";
import { SettingsView, applyTheme } from "./views/Settings";

function Routed() {
  const { route, campaign, campaignError, dev, go } = useApp();
  if (!route.campaignId) return <PickerView />;
  if (campaignError)
    return (
      <div className="picker">
        <div className="error-box">{campaignError}</div>
        <button className="btn" onClick={() => go({ campaignId: null })}>
          Back to campaigns
        </button>
      </div>
    );
  if (!campaign) return <div className="picker muted">Opening the campaign…</div>;
  const view = route.view === "debug" && !dev ? "play" : route.view;
  const body = {
    play: <PlayView />,
    character: <CharacterView />,
    party: <PartyView />,
    journal: <JournalView />,
    encyclopedia: <EncyclopediaView />,
    world: <WorldView />,
    settings: <SettingsView />,
    debug: <DebugView />,
  }[view];
  // the right-hand panel accompanies play on wide screens
  return <Shell side={view === "play" ? <SidePanel /> : undefined}>{body}</Shell>;
}

export default function App() {
  useEffect(() => applyTheme(readPref("theme", "system")), []);
  return (
    <AppProvider>
      <TurnsProvider>
        <Routed />
      </TurnsProvider>
    </AppProvider>
  );
}
