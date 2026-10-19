import React from "react";

export const nf = new Intl.NumberFormat("en-US");
export const fmt = (n) => (n === null || n === undefined ? "n/a" : nf.format(Math.round(n)));
export const fmtCost = (n) => (n === null || n === undefined ? "n/a" : `$${Number(n).toFixed(n < 1 ? 4 : 2)}`);
export const fmtPct = (n) => (n === null || n === undefined ? "n/a" : `${Number(n).toFixed(1)}%`);

const GLYPH = { PASSED: "✓", SKIPPED: "↷", RUNNING: "●", PENDING: "○", FAILED: "✕", BLOCKED: "!", COMPLETED: "✓" };
const TONE = {
  PASSED: "good", COMPLETED: "good", SKIPPED: "skip", RUNNING: "info",
  PENDING: "neutral", FAILED: "crit", BLOCKED: "warn", PAUSED: "warn",
};

/** Status chip: colour is never the only signal, a glyph and the word always travel with it. */
export function Badge({ status, label }) {
  const key = String(status || "").toUpperCase();
  return (
    <span className={`badge tone-${TONE[key] || "neutral"}`}>
      <span aria-hidden="true">{GLYPH[key] || "·"}</span> {label || status || "unknown"}
    </span>
  );
}

export function Bar({ percent, label, tone = "info" }) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  return (
    <div className="bar" role="img" aria-label={`${label || "progress"} ${value.toFixed(1)}%`}>
      <div className={`bar-fill tone-${tone}`} style={{ width: `${value}%` }} />
    </div>
  );
}

export function Card({ title, children, aside }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {aside ? <div className="muted">{aside}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}

export function Stat({ label, value, hint }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

export function Table({ columns, rows, empty = "Nothing to show yet." }) {
  if (!rows || rows.length === 0) return <Empty>{empty}</Empty>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.key ?? i}>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(row) : row[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function shortTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleTimeString();
}
