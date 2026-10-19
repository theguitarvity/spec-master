import { useCallback, useEffect, useRef, useState } from "react";

// Event names the server may emit (docs/contracts/token-ledger-v1.md §4). EventSource needs
// one listener per name; unknown record types fall back to the generic "event" name.
export const EVENT_TYPES = [
  "model", "tokens", "hook.fired", "hook.decision", "change", "event",
  "phase.started", "phase.finished", "agent.started", "agent.finished", "gate.result",
];

const FEED_LIMIT = 200;
const REFETCH_DEBOUNCE_MS = 800;
const POLL_FALLBACK_MS = 30000;

export async function fetchModel(signal) {
  const res = await fetch("api/model", { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`api/model answered ${res.status}`);
  return res.json();
}

/** Live model: initial fetch, SSE-driven refetch (debounced), slow poll as a safety net. */
export function useLive() {
  const [model, setModel] = useState(null);
  const [status, setStatus] = useState("connecting");
  const [error, setError] = useState(null);
  const [feed, setFeed] = useState([]);
  const timer = useRef(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchModel();
      if (alive.current) { setModel(next); setError(null); }
    } catch (e) {
      if (alive.current) setError(String(e.message || e));
    }
  }, []);

  const schedule = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(refresh, REFETCH_DEBOUNCE_MS);
  }, [refresh]);

  useEffect(() => {
    alive.current = true;
    refresh();
    const poll = setInterval(refresh, POLL_FALLBACK_MS);
    const source = new EventSource("api/events");
    source.onopen = () => setStatus("live");
    source.onerror = () => setStatus(source.readyState === EventSource.CLOSED ? "offline" : "reconnecting");
    const handlers = EVENT_TYPES.map((type) => {
      const handler = (msg) => {
        let data = null;
        try { data = JSON.parse(msg.data); } catch { /* keep raw */ }
        setFeed((old) => [{ at: Date.now(), type, data }, ...old].slice(0, FEED_LIMIT));
        schedule();
      };
      source.addEventListener(type, handler);
      return [type, handler];
    });
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
      clearInterval(poll);
      handlers.forEach(([type, handler]) => source.removeEventListener(type, handler));
      source.close();
    };
  }, [refresh, schedule]);

  return { model, status, error, feed, refresh };
}
