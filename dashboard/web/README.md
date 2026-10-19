# Spec Master Live dashboard (UI source)

React 18 + Vite app served by `python3 spec-master/lib/cli.py dashboard serve`.

## Principle IX exception

Spec Master's core is Python stdlib only. This directory is the one isolated place that uses
Node, and only to **rebuild** the UI:

- The built bundle in `dist/` is **committed**. Running the dashboard needs Python only, no Node.
- `dist/MANIFEST.json` holds a sha256 per file. `spec-master/tests/test_dashboard_bundle.py`
  checks it, so a stale or hand-edited bundle fails the suite. Tests never run Node.
- `node_modules/` is git-ignored and never shipped in the plugin package.

## Rebuild

```
cd dashboard/web
npm install
npm run build      # vite build, then regenerates dist/MANIFEST.json
```

Development with hot reload: start `dashboard serve` (port 8765), then `npm run dev`
(Vite proxies `/api` to it).
