import { defineConfig } from "vite";

// Root is web/: index.html en src/ staan daar, web/public/ (uitlegschetsen) wordt naar web/dist/ gekopieerd.
// base "./" houdt de paden relatief; three.js wordt in de bundel opgenomen, dus de app werkt zonder internet.
export default defineConfig({
  root: "web",
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: { proxy: { "/api": { target: "http://127.0.0.1:8011", ws: true } } },
});
