import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "prompt-architect-dev-origin",
      configureServer(server) {
        server.middlewares.use((request, _response, next) => {
          const incoming = request as unknown as {
            url?: string;
            headers: Record<string, string | string[] | undefined>;
          };
          if (incoming.url?.startsWith("/api")) {
            incoming.headers.origin = "http://127.0.0.1:8765";
          }
          next();
        });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../prompt_architect/web/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
