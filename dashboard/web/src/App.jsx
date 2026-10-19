import React, { useState } from "react";
import { useLive } from "./api.js";
import { Empty } from "./ui.jsx";
import {
  Overview, Features, Timeline, Tokens, Agents, GatesHooks, Dependencies, Feed,
} from "./views.jsx";

const TABS = [
  ["overview", "Overview", Overview],
  ["features", "Features", Features],
  ["timeline", "Timeline", Timeline],
  ["tokens", "Tokens", Tokens],
  ["agents", "Agents & lanes", Agents],
  ["gates", "Gates & hooks", GatesHooks],
  ["deps", "Dependencies", Dependencies],
  ["feed", "Live feed", Feed],
];

const STATUS_TEXT = {
  live: "● live", connecting: "◌ connecting", reconnecting: "◌ reconnecting", offline: "✕ offline",
};

export default function App() {
  const { model, status, error, feed } = useLive();
  const [tab, setTab] = useState(() => {
    const hash = window.location.hash.replace("#", "");
    return TABS.some(([id]) => id === hash) ? hash : "overview";
  });
  const select = (id) => { setTab(id); window.location.hash = id; };
  const View = TABS.find(([id]) => id === tab)[2];

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Spec Master Live</h1>
          <div className="muted">{model ? `${model.project} · ${model.workflow?.status || "uninitialized"}` : "loading"}</div>
        </div>
        <div className={`conn conn-${status}`} role="status" aria-live="polite">{STATUS_TEXT[status] || status}</div>
      </header>
      <nav className="tabs" role="tablist" aria-label="Dashboard views">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "tab on" : "tab"}
                  onClick={() => select(id)}>{label}</button>
        ))}
      </nav>
      <main>
        {error ? <div className="alert" role="alert">✕ Could not refresh the model: {error}</div> : null}
        {model ? <View model={model} feed={feed} /> : <Empty>Loading the model…</Empty>}
      </main>
    </div>
  );
}
