import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Mirrors infrastructure/nginx/nginx.conf's routing so `npm run dev` against a
    // locally running backend behaves the same as the full docker-compose stack —
    // without this, a relative /api/v1/... request hits Vite's own SPA fallback instead
    // of the backend, which returns index.html with a 200 and masks the failure.
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: { "@": "/src" },
  },
});
