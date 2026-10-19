import React, { useMemo, useState } from "react";
import { Badge, Bar, Card, Empty, Stat, Table, fmt, fmtCost, fmtPct, shortTime } from "./ui.jsx";

const PHASES = ["specify", "clarify", "plan", "tasks", "analyze", "implement", "validate"];

/* ------------------------------------------------------------------ Overview */
export function Overview({ model }) {
  const run = model.run || {};
  const totals = model.phase_totals || {};
  return (
    <>
      <Card title="Run state" aside={run.reason}>
        <div className="stats">
          <Stat label="State" value={<Badge status={run.active ? "RUNNING" : "PENDING"} label={run.state || "idle"} />} />
          <Stat label="Features" value={`${model.completeness?.features_done ?? 0} / ${model.completeness?.features ?? 0}`} hint="completed" />
          <Stat label="Phases" value={`${model.completeness?.done ?? 0} / ${model.completeness?.total ?? 0}`} hint="passed in the flow" />
          <Stat label="Errors" value={(model.errors || []).length} hint={(model.errors || []).length ? "see list below" : "none"} />
        </div>
      </Card>
      <Card title="Progress per cycle" aside="completed-outside-flow features count as done">
        {(model.cycles || []).length === 0 ? <Empty>No cycles recorded.</Empty> : (model.cycles || []).map((c) => (
          <div key={c.id} className="cycle-row">
            <div className="cycle-head">
              <strong>Cycle {c.id}</strong> <Badge status={c.status} />
              <span className="muted"> {c.features_completed}/{c.features} features · {c.done}/{c.total} phases passed</span>
              <span className="pct">{fmtPct(c.effective_percent)}</span>
            </div>
            <Bar percent={c.effective_percent} label={`Cycle ${c.id}`} tone={c.status === "COMPLETED" ? "good" : "info"} />
          </div>
        ))}
      </Card>
      <Card title="Phase totals">
        <div className="chips">
          {Object.keys(totals).length === 0 ? <Empty>No phases yet.</Empty> :
            Object.entries(totals).map(([k, v]) => <span key={k} className="chip"><Badge status={k} /> <b>{v}</b></span>)}
        </div>
      </Card>
      {(model.errors || []).length ? (
        <Card title="Errors">
          <ul className="plain">{model.errors.map((e, i) => <li key={i}>✕ {typeof e === "string" ? e : JSON.stringify(e)}</li>)}</ul>
        </Card>
      ) : null}
    </>
  );
}

/* ------------------------------------------------------------------ Features */
export function Features({ model }) {
  const [cycle, setCycle] = useState("all");
  const cycles = [...new Set((model.features || []).map((f) => f.cycle || 1))].sort();
  const shown = (model.features || []).filter((f) => cycle === "all" || String(f.cycle || 1) === cycle);
  const columns = [...PHASES, "done"];
  const bucket = (f) => (f.status === "COMPLETED" ? "done" : (f.current_phase || "specify"));
  return (
    <>
      <div className="filters" role="group" aria-label="Cycle filter">
        <label>Cycle <select value={cycle} onChange={(e) => setCycle(e.target.value)}>
          <option value="all">all</option>
          {cycles.map((c) => <option key={c} value={String(c)}>{c}</option>)}
        </select></label>
        <span className="muted">{shown.length} features</span>
      </div>
      <div className="kanban">
        {columns.map((col) => {
          const items = shown.filter((f) => bucket(f) === col);
          return (
            <section key={col} className="lane-col" aria-label={col}>
              <h3>{col} <span className="count">{items.length}</span></h3>
              {items.map((f) => (
                <article key={f.id} className="kcard">
                  <div className="kname">{f.name || f.id}</div>
                  <div className="muted mono">{f.id}</div>
                  <Bar percent={f.effective_percent} label={f.id} tone={f.status === "COMPLETED" ? "good" : "info"} />
                  <div className="kmeta">
                    <Badge status={f.status} />
                    <span className="muted">C{f.cycle || 1}{f.risk_tier ? ` · tier ${f.risk_tier}` : ""}</span>
                  </div>
                  {f.delivery ? <div className="muted small">delivered outside the flow (phases not tracked)</div> : null}
                </article>
              ))}
            </section>
          );
        })}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Timeline */
export function Timeline({ model }) {
  const rows = model.timeline || [];
  const { t0, span } = useMemo(() => {
    const times = rows.flatMap((r) => [Date.parse(r.started_at), Date.parse(r.finished_at || r.started_at)]).filter(Number.isFinite);
    const min = Math.min(...times, Date.now());
    const max = Math.max(...times, Date.now());
    return { t0: min, span: Math.max(max - min, 1) };
  }, [rows]);
  const m = model.metrics || {};
  return (
    <>
      <Card title="Metrics summary">
        <div className="stats">
          <Stat label="Rounds" value={fmt(m.rounds)} />
          <Stat label="Duration" value={m.duration_seconds != null ? `${(m.duration_seconds / 60).toFixed(1)} min` : "n/a"} />
          <Stat label="Packages / hour" value={m.packages_per_hour ?? "n/a"} />
          <Stat label="Features / hour" value={m.features_per_hour ?? "n/a"} />
        </div>
      </Card>
      <Card title="Phase timeline" aside="from events.jsonl">
        {rows.length === 0 ? <Empty>No phase events yet. They appear once the harness records phase.started / phase.finished.</Empty> : (
          <div className="gantt">
            {rows.map((r, i) => {
              const start = Date.parse(r.started_at);
              const end = Date.parse(r.finished_at || new Date().toISOString());
              const left = ((start - t0) / span) * 100;
              const width = Math.max(((end - start) / span) * 100, 1.5);
              return (
                <div key={i} className="gantt-row">
                  <div className="gantt-label mono">{r.feature_id}:{r.phase}</div>
                  <div className="gantt-track">
                    <div className={`gantt-bar tone-${r.finished_at ? "good" : "info"}`} style={{ left: `${left}%`, width: `${width}%` }}
                         title={`${r.started_at} → ${r.finished_at || "running"}`}>
                      {r.finished_at ? "✓" : "●"} {r.status}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ Tokens */
function breakdown(obj, label) {
  const rows = Object.entries(obj || {}).map(([k, v]) => ({ key: k, name: k, ...v }));
  return (
    <Card title={`By ${label}`}>
      <Table rows={rows} empty={`No ${label} data in the ledger yet.`} columns={[
        { key: "name", label },
        { key: "total_tokens", label: "Total", num: true, render: (r) => fmt(r.total_tokens) },
        { key: "input_tokens", label: "Input", num: true, render: (r) => fmt(r.input_tokens) },
        { key: "output_tokens", label: "Output", num: true, render: (r) => fmt(r.output_tokens) },
        { key: "cost_usd", label: "Cost", num: true, render: (r) => fmtCost(r.cost_usd) },
      ]} />
    </Card>
  );
}

export function Tokens({ model }) {
  const t = model.tokens;
  if (!t) {
    return (
      <Card title="Tokens">
        <Empty>Token ledger not available. It appears once the token-ledger feature records usage; nothing is estimated.</Empty>
        <p className="muted">Tier budget: not configured.</p>
      </Card>
    );
  }
  const totals = t.totals || {};
  return (
    <>
      <Card title="Totals" aside={t.window ? `${shortTime(t.window.first_ts)} → ${shortTime(t.window.last_ts)}` : "no window"}>
        <div className="stats">
          <Stat label="Total tokens" value={fmt(totals.total_tokens)} />
          <Stat label="Burn rate" value={`${fmt(t.burn_rate_tokens_per_min)} /min`} />
          <Stat label="Cache hit" value={fmtPct((totals.cache_hit_ratio ?? 0) * 100)} />
          <Stat label="Cost" value={fmtCost(totals.cost_usd)} />
          <Stat label="Tier budget" value="not configured" hint="no budget set" />
        </div>
      </Card>
      {breakdown(t.by_feature, "feature")}
      {breakdown(t.by_phase, "phase")}
      {breakdown(t.by_agent, "agent")}
      {breakdown(t.by_model, "model")}
    </>
  );
}

/* ------------------------------------------------------------------ Agents & lanes */
export function Agents({ model }) {
  const agents = model.agents || [];
  const pkgs = model.workstreams?.packages || [];
  const lanes = model.lanes || { active: null, recent: [] };
  return (
    <>
      <Card title="Agents" aside="from events.jsonl">
        <Table rows={agents} empty="No agent events yet." columns={[
          { key: "agent_id", label: "Agent", render: (r) => <span className="mono">{r.agent_id}</span> },
          { key: "agent_type", label: "Type" },
          { key: "feature_id", label: "Feature" },
          { key: "phase", label: "Phase" },
          { key: "active", label: "State", render: (r) => <Badge status={r.active ? "RUNNING" : "PASSED"} label={r.active ? "active" : "finished"} /> },
        ]} />
      </Card>
      <Card title="Work packages">
        <Table rows={pkgs} empty="No work packages." columns={[
          { key: "id", label: "Package", render: (r) => <span className="mono">{r.id}</span> },
          { key: "title", label: "Title" },
          { key: "owner", label: "Owner" },
          { key: "status", label: "Status", render: (r) => <Badge status={r.status === "review_pending" ? "PENDING" : String(r.status).toUpperCase()} label={r.status} /> },
        ]} />
      </Card>
      <Card title="Change lanes">
        <p className="muted">Active: {lanes.active ? <span className="mono">{JSON.stringify(lanes.active)}</span> : "none"}</p>
        <Table rows={lanes.recent || []} empty="No recent changes." columns={[
          { key: "id", label: "Change", render: (r) => <span className="mono">{r.id || r.change_id || "?"}</span> },
          { key: "lane", label: "Lane" },
          { key: "status", label: "Status" },
        ]} />
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ Gates & hooks */
export function GatesHooks({ model }) {
  return (
    <>
      <Card title="Gates">
        <Table rows={model.gates || []} empty="No gate results recorded." columns={[
          { key: "name", label: "Gate", render: (r) => r.name || r.gate || r.id },
          { key: "status", label: "Status", render: (r) => <Badge status={String(r.status || r.result || "").toUpperCase()} label={r.status || r.result} /> },
          { key: "detail", label: "Detail", render: (r) => r.detail || r.command || "" },
        ]} />
      </Card>
      <Card title="Hook firings">
        <Table rows={(model.hooks || []).slice(0, 30)} empty="No hook firings." columns={[
          { key: "at", label: "At", render: (r) => shortTime(r.at) },
          { key: "type", label: "Event" },
          { key: "fired", label: "Hooks", render: (r) => (r.fired || []).map((f) => `${f.error ? "✕" : "✓"} ${f.hook}`).join(", ") },
        ]} />
      </Card>
      <Card title="Hook decisions" aside="audit mode logs without blocking">
        <Table rows={model.hook_decisions || []} empty="No hook decisions logged." columns={[
          { key: "at", label: "At", render: (r) => shortTime(r.at) },
          { key: "event", label: "Event" },
          { key: "tool", label: "Tool" },
          { key: "decision", label: "Decision", render: (r) => <Badge status={r.decision === "allow" ? "PASSED" : "BLOCKED"} label={`${r.decision}${r.enforced ? "" : " (audit)"}`} /> },
          { key: "reason", label: "Reason" },
        ]} />
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ Dependencies */
export function Dependencies({ model }) {
  const features = model.features || [];
  const layout = useMemo(() => {
    const byId = Object.fromEntries(features.map((f) => [f.id, f]));
    const depth = {};
    const visit = (id, seen = new Set()) => {
      if (depth[id] != null) return depth[id];
      if (seen.has(id) || !byId[id]) return 0;
      seen.add(id);
      const d = (byId[id].dependencies || []).filter((x) => byId[x]).reduce((m, x) => Math.max(m, visit(x, seen) + 1), 0);
      depth[id] = d;
      return d;
    };
    features.forEach((f) => visit(f.id));
    const cols = {};
    features.forEach((f) => { (cols[depth[f.id] || 0] ||= []).push(f); });
    const pos = {};
    Object.entries(cols).forEach(([c, list]) => list.forEach((f, i) => { pos[f.id] = { x: 20 + Number(c) * 230, y: 20 + i * 56 }; }));
    const edges = features.flatMap((f) => (f.dependencies || []).filter((d) => pos[d]).map((d) => [d, f.id]));
    const width = 20 + (Math.max(0, ...Object.keys(cols).map(Number)) + 1) * 230;
    const height = 40 + Math.max(1, ...Object.values(cols).map((l) => l.length)) * 56;
    return { pos, edges, width, height };
  }, [features]);
  return (
    <>
      <Card title="Feature dependencies" aside="arrows point from dependency to dependant">
        {features.length === 0 ? <Empty>No features.</Empty> : (
          <div className="svg-wrap">
            <svg width={layout.width} height={layout.height} role="img" aria-label="Feature dependency graph">
              <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" className="arrow" /></marker></defs>
              {layout.edges.map(([a, b], i) => {
                const p = layout.pos[a]; const q = layout.pos[b];
                return <line key={i} x1={p.x + 200} y1={p.y + 20} x2={q.x} y2={q.y + 20} className="edge" markerEnd="url(#arrow)" />;
              })}
              {features.map((f) => {
                const p = layout.pos[f.id];
                return (
                  <g key={f.id} transform={`translate(${p.x},${p.y})`}>
                    <rect width="200" height="40" rx="6" className={`node tone-${f.status === "COMPLETED" ? "good" : "info"}`} />
                    <text x="8" y="17" className="node-text">{(f.status === "COMPLETED" ? "✓ " : "● ") + f.id.slice(0, 26)}</text>
                    <text x="8" y="32" className="node-sub">C{f.cycle || 1} · {f.current_phase || f.status}</text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </Card>
      <Card title="System map">
        {model.graph?.system_map ? <pre className="pre">{model.graph.system_map}</pre> : <Empty>No knowledge graph yet.</Empty>}
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ Live feed */
export function Feed({ feed }) {
  return (
    <Card title="Live feed" aside="newest first, kept in memory only">
      {feed.length === 0 ? <Empty>Waiting for events. Anything appended to the ledgers shows up here.</Empty> : (
        <ul className="feed">
          {feed.map((e, i) => (
            <li key={i}><span className="muted mono">{new Date(e.at).toLocaleTimeString()}</span> <b>{e.type}</b>{" "}
              <span className="mono small">{e.data ? JSON.stringify(e.data).slice(0, 180) : ""}</span></li>
          ))}
        </ul>
      )}
    </Card>
  );
}
