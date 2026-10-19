import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base: the bundle works when served from "/" by `spec-master dashboard serve`
// and from any sub-path. Deterministic output (no source maps) keeps the committed
// bundle and its MANIFEST.json reviewable.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, target: "es2020" },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
