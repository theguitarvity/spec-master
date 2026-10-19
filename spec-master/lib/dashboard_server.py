"""Live dashboard server (`dashboard serve`): stdlib SSE + the committed React bundle.

Consumer of `docs/contracts/token-ledger-v1.md` §3-§4. Read-only: it never
writes project state. It binds to 127.0.0.1 only, answers GET/HEAD only and
rejects any `Host` header that is not loopback (DNS-rebinding guard).

Routes
------
* `GET /api/model`  -> `dashboard.build_model(root)` plus `tokens` (ledger
  aggregate or null), `agents` and `timeline` (derived from `events.jsonl`).
* `GET /api/events` -> Server-Sent Events. New lines of `events.jsonl`
  (`event: <record type>`), `metrics/tokens.jsonl` (`tokens`),
  `hooks/firings.jsonl` (`hook.fired`), `hooks/decisions.jsonl`
  (`hook.decision`), the `changes/` records (`change`) and `state.json`
  (`model`). Only lines appended after the client connected are sent.
  A `: ping` heartbeat is sent every 15 s.
* `GET /healthz`, and the static bundle (`dashboard/web/dist`) for everything
  else; when the bundle is absent `/` serves the static HTML dashboard so the
  fallback of Principle VI keeps working.

The UI under `dashboard/web/` is the only Node-dependent part of the project
(Principle IX exception, see its README). Node is needed to REBUILD it, never
to run it: the built bundle is committed and verified by `MANIFEST.json`.

Importing this module does not import the ledger: it is looked up lazily and
optionally (feature 14 may not be present), see `tokens_summary`.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import mimetypes
import os
import socketserver
import sys
import tempfile
import threading
import time
import urllib.parse

import dashboard

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HEARTBEAT_SECONDS = 15.0
POLL_INTERVAL = 0.5
MAX_CLIENTS = 32
EVENTS_TAIL_RECORDS = 2000
MAX_TIMELINE = 200
MAX_AGENTS = 100
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")
MANIFEST_NAME = "MANIFEST.json"
MANIFEST_SCHEMA = "spec-master.dashboard-bundle/v1"
DEFAULT_DIST = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "..", "..", "dashboard", "web", "dist"))
BUNDLE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")

_AUTO = object()
_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
          ".json": "application/json", ".svg": "image/svg+xml", ".map": "application/json",
          ".woff2": "font/woff2", ".ico": "image/x-icon", ".png": "image/png"}


# ---------------------------------------------------------------- tailing

class Tailer:
    """Yields JSON objects appended to a JSONL file after construction.

    Starts at end-of-file (a client only wants *new* lines), holds a partial
    trailing line until its newline arrives, restarts from 0 when the file
    shrinks and silently skips corrupt or non-object lines.
    """

    def __init__(self, path: str):
        self.path = path
        self._buf = b""
        self.offset = self._size() or 0

    def _size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return None

    def poll(self) -> list:
        size = self._size()
        if size is None:
            return []
        if size < self.offset:  # truncated or rotated
            self.offset, self._buf = 0, b""
        if size == self.offset:
            return []
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.offset)
                chunk = fh.read(size - self.offset)
        except OSError:
            return []
        self.offset += len(chunk)
        data = self._buf + chunk
        parts = data.split(b"\n")
        self._buf = parts.pop()  # "" when the chunk ended with a newline
        out = []
        for raw in parts:
            try:
                record = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(record, dict):
                out.append(record)
        return out


def _clean(text) -> str:
    return " ".join(str(text).split())


def format_sse(event: str, data: str) -> str:
    return f"event: {_clean(event)}\ndata: {_clean(data)}\n\n"


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _signature(path: str):
    try:
        stat = os.stat(path)
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


class LiveSources:
    """All watched files of one project. `poll()` -> [(event name, one-line JSON)]."""

    def __init__(self, root: str):
        sm = os.path.join(os.path.abspath(root), ".spec-master")
        self.state_path = os.path.join(sm, "state.json")
        self.changes_dir = os.path.join(sm, "changes")
        self.tailers = [
            (Tailer(os.path.join(sm, "events.jsonl")), None),
            (Tailer(os.path.join(sm, "metrics", "tokens.jsonl")), "tokens"),
            (Tailer(os.path.join(sm, "hooks", "firings.jsonl")), "hook.fired"),
            (Tailer(os.path.join(sm, "hooks", "decisions.jsonl")), "hook.decision"),
        ]
        self._state_sig = _signature(self.state_path)
        self._changes = self._scan_changes()

    def _scan_changes(self) -> dict:
        out = {}
        try:
            names = os.listdir(self.changes_dir)
        except OSError:
            return out
        for name in names:
            if name.endswith(".json") and name != "active.json":
                out[name] = _signature(os.path.join(self.changes_dir, name))
        return out

    def _change_payload(self, name: str) -> dict:
        change_id = name[:-len(".json")]
        try:
            with open(os.path.join(self.changes_dir, name), "r", encoding="utf-8") as fh:
                record = json.load(fh)
            payload = {"id": change_id}
            for key in ("status", "updated_at"):
                if isinstance(record.get(key), str):
                    payload[key] = record[key]
            return payload
        except (OSError, ValueError, AttributeError):
            return {"id": change_id}

    def poll(self) -> list:
        events = []
        for tailer, fixed in self.tailers:
            for record in tailer.poll():
                if fixed:
                    name = fixed
                else:
                    kind = record.get("type")
                    name = kind if isinstance(kind, str) and kind.strip() else "event"
                events.append((name, _dumps(record)))
        current = self._scan_changes()
        for name in sorted(current):
            if self._changes.get(name) != current[name]:
                events.append(("change", _dumps(self._change_payload(name))))
        self._changes = current
        sig = _signature(self.state_path)
        if sig != self._state_sig:
            self._state_sig = sig
            events.append(("model", _dumps({"generated_at": dashboard._iso(dashboard._now()),
                                            "reason": "state.json changed"})))
        return events


# ---------------------------------------------------------------- model

def derive_events(records) -> dict:
    """Active/finished agents and phase intervals from `events.jsonl` records (contract §1)."""
    timeline, agents = [], {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        kind, ts = rec.get("type"), rec.get("ts")
        if kind == "phase.started":
            timeline.append({"feature_id": rec.get("feature_id"), "phase": rec.get("phase"),
                             "session_id": rec.get("session_id"), "started_at": ts,
                             "finished_at": None, "status": "RUNNING"})
        elif kind == "phase.finished":
            key = (rec.get("session_id"), rec.get("feature_id"), rec.get("phase"))
            for entry in reversed(timeline):
                if entry["finished_at"] is None and \
                        (entry["session_id"], entry["feature_id"], entry["phase"]) == key:
                    entry["finished_at"] = ts
                    entry["status"] = rec.get("status") if isinstance(rec.get("status"), str) else "FINISHED"
                    break
        elif kind == "agent.started" and isinstance(rec.get("agent_id"), str):
            agents[rec["agent_id"]] = {
                "agent_id": rec["agent_id"], "agent_type": rec.get("agent_type"),
                "worktree": rec.get("worktree"), "feature_id": rec.get("feature_id"),
                "phase": rec.get("phase"), "started_at": ts, "finished_at": None, "active": True}
        elif kind == "agent.finished" and rec.get("agent_id") in agents:
            agents[rec["agent_id"]].update(finished_at=ts, active=False)
    return {"agents": list(agents.values())[-MAX_AGENTS:], "timeline": timeline[-MAX_TIMELINE:]}


def tokens_summary(root: str, provider=None, ledger_module=_AUTO):
    """Contract §3 aggregate, or None when there is no ledger (or it fails).

    `provider(root)` wins (tests, embedding). Otherwise the optional `ledger`
    module (feature 14) is asked via `summarize(root)` or `summary(root)`.
    This server never parses transcripts or the tokens JSONL itself.
    """
    try:
        if provider is not None:
            result = provider(root)
        else:
            module = ledger_module
            if module is _AUTO:
                try:
                    import ledger as module  # noqa: PLC0415 -- optional, produced by feature 14
                except ImportError:
                    module = None
            func = getattr(module, "summarize", None) or getattr(module, "summary", None) if module else None
            result = func(root) if callable(func) else None
    except Exception:  # noqa: BLE001 -- a broken ledger must not take the dashboard down
        return None
    return result if isinstance(result, dict) else None


def build_live_model(root: str, provider=None, ledger_module=_AUTO) -> dict:
    model = dashboard.build_model(root)
    records = dashboard._tail_jsonl(os.path.join(os.path.abspath(root), ".spec-master", "events.jsonl"),
                                    EVENTS_TAIL_RECORDS)
    model["tokens"] = tokens_summary(root, provider=provider, ledger_module=ledger_module)
    model.update(derive_events(records))
    return model


# ---------------------------------------------------------------- bundle manifest

def _bundle_files(dist: str) -> dict:
    out = {}
    for dirpath, _dirs, files in os.walk(dist):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, dist).replace(os.sep, "/")
            if rel == MANIFEST_NAME:
                continue
            with open(full, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(out.items()))


def manifest(dist: str) -> dict:
    return {"schema": MANIFEST_SCHEMA, "files": _bundle_files(dist)}


def write_manifest(dist: str) -> dict:
    data = manifest(dist)
    fd, tmp = tempfile.mkstemp(dir=dist, prefix=".manifest-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, os.path.join(dist, MANIFEST_NAME))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return data


def verify_manifest(dist: str) -> list:
    """Problems between the committed manifest and the files on disk ([] = intact)."""
    path = os.path.join(dist, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            expected = json.load(fh).get("files")
        if not isinstance(expected, dict):
            raise ValueError("no files map")
    except (OSError, ValueError, AttributeError):
        return [f"missing manifest: {MANIFEST_NAME}"]
    actual = _bundle_files(dist)
    problems = [f"missing: {rel}" for rel in sorted(expected) if rel not in actual]
    problems += [f"modified: {rel}" for rel in sorted(expected) if rel in actual and actual[rel] != expected[rel]]
    problems += [f"unlisted: {rel}" for rel in sorted(actual) if rel not in expected]
    return problems


# ---------------------------------------------------------------- HTTP

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "SpecMasterDashboard"
    sys_version = ""

    def log_message(self, *args):  # quiet: stdout carries the one JSON line of `dashboard serve`
        return

    # -- plumbing
    def _send(self, status, body=b"", content_type="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, value):
        self._send(status, _dumps(value).encode("utf-8"), extra={"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        host = self.headers.get("Host")
        if host is None:
            return True  # HTTP/1.0 client: nothing to rebind
        name = host.rsplit(":", 1)[0] if not host.endswith("]") and ":" in host else host
        return name.lower() in ALLOWED_HOSTS

    def _method_not_allowed(self):
        self._send(405, b'{"error":"method not allowed"}', extra={"Allow": "GET, HEAD"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/model":
            return self._json(200, build_live_model(self.server.root, provider=self.server.tokens_provider))
        if path == "/api/events":
            return self._events()
        if path == "/healthz":
            return self._json(200, {"ok": True})
        if path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        return self._static(path)

    # -- static bundle (+ static HTML fallback)
    def _static(self, path):
        dist = os.path.realpath(self.server.dist_dir)
        index = os.path.join(dist, "index.html")
        if not os.path.isfile(index):
            if path in ("/", "/index.html"):
                html = dashboard.render_html(dashboard.build_model(self.server.root)).encode("utf-8")
                return self._send(200, html, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
            return self._json(404, {"error": "not found"})
        rel = urllib.parse.unquote(path).lstrip("/")
        if "\0" in rel:
            return self._json(400, {"error": "bad path"})
        target = os.path.realpath(os.path.join(dist, rel)) if rel else dist
        if target != dist and not target.startswith(dist + os.sep):
            return self._json(403, {"error": "forbidden"})
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            return self._json(404, {"error": "not found"})
        with open(target, "rb") as fh:
            body = fh.read()
        ext = os.path.splitext(target)[1].lower()
        ctype = _TYPES.get(ext) or mimetypes.guess_type(target)[0] or "application/octet-stream"
        extra = {"Content-Security-Policy": BUNDLE_CSP}
        if ext == ".html":
            extra["Cache-Control"] = "no-store"
        return self._send(200, body, ctype, extra)

    # -- SSE
    def _events(self):
        server = self.server
        if not server.acquire_client():
            return self._json(503, {"error": "too many live clients"})
        try:
            sources = LiveSources(server.root)  # offsets fixed BEFORE announcing the connection
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            last_beat = time.monotonic()
            while not server.stop_event.is_set():
                chunk = "".join(format_sse(name, data) for name, data in sources.poll())
                now = time.monotonic()
                if not chunk and now - last_beat >= server.heartbeat:
                    chunk = ": ping\n\n"
                if chunk:
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                    last_beat = now
                server.stop_event.wait(server.poll_interval)
        except (OSError, ValueError):
            pass  # client went away
        finally:
            server.release_client()
            self.close_connection = True


class LiveServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, address, root, dist_dir, heartbeat, poll_interval, tokens_provider, max_clients):
        self.root = os.path.abspath(root)
        self.dist_dir = dist_dir
        self.heartbeat = heartbeat
        self.poll_interval = poll_interval
        self.tokens_provider = tokens_provider
        self.max_clients = max_clients
        self.stop_event = threading.Event()
        self.active_clients = 0
        self._clients_lock = threading.Lock()
        super().__init__(address, Handler)

    def server_bind(self):  # skip HTTPServer's getfqdn(): slow, and irrelevant on loopback
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = HOST, self.server_address[1]

    def acquire_client(self) -> bool:
        with self._clients_lock:
            if self.active_clients >= self.max_clients:
                return False
            self.active_clients += 1
            return True

    def release_client(self) -> None:
        with self._clients_lock:
            self.active_clients = max(0, self.active_clients - 1)

    def shutdown(self):
        self.stop_event.set()
        super().shutdown()


def make_server(root: str, port: int = DEFAULT_PORT, dist_dir: str | None = None,
                heartbeat: float = HEARTBEAT_SECONDS, poll_interval: float = POLL_INTERVAL,
                tokens_provider=None, max_clients: int = MAX_CLIENTS) -> LiveServer:
    """Server bound to 127.0.0.1 ONLY (port 0 = ephemeral). The caller runs `serve_forever`."""
    return LiveServer((HOST, port), root, dist_dir or DEFAULT_DIST, heartbeat, poll_interval,
                      tokens_provider, max_clients)


def serve(root: str, port: int = DEFAULT_PORT, open_browser: bool = False, ready=None, out=None) -> int:
    out = out or sys.stdout
    try:
        server = make_server(root, port)
    except OSError as exc:
        print(_dumps({"error": f"cannot bind {HOST}:{port}: {exc}"}), file=sys.stderr)
        return 1
    url = f"http://{HOST}:{server.server_address[1]}/"
    bundle = os.path.isfile(os.path.join(server.dist_dir, "index.html"))
    print(_dumps({"url": url, "port": server.server_address[1], "root": server.root, "bundle": bundle}),
          file=out, flush=True)
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 -- opening a browser is a convenience only
            pass
    if ready:
        ready(server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_event.set()
        server.server_close()
    return 0


def main(argv=None) -> int:
    """`python3 dashboard_server.py manifest [--dist DIR] [--check]` (used by `npm run build`)."""
    import argparse
    parser = argparse.ArgumentParser(prog="dashboard_server")
    sub = parser.add_subparsers(dest="action", required=True)
    man = sub.add_parser("manifest", help="write (or --check) dashboard/web/dist/MANIFEST.json")
    man.add_argument("--dist", default=DEFAULT_DIST)
    man.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        problems = verify_manifest(args.dist)
        print(_dumps({"ok": not problems, "problems": problems}))
        return 1 if problems else 0
    data = write_manifest(args.dist)
    print(_dumps({"written": os.path.join(args.dist, MANIFEST_NAME), "files": len(data["files"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
