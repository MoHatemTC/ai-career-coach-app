import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to FastAPI so the browser only ever talks to one
// origin. CORS is still configured backend-side, because a production build
// served from nginx does not go through this proxy.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        // The backend does not version its routes yet, so /api is stripped
        // here. When PR 0 lands /api/v1 server-side, delete this rewrite.
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
