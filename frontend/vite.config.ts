import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const path = (relative: string) =>
  fileURLToPath(new URL(relative, import.meta.url));
const target = process.env.REELFORGE_API_TARGET || "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  optimizeDeps: { include: ["@tanstack/react-virtual"] },
  resolve: {
    alias: {
      "@": path("./src"),
      "@motion": path("../motion/src"),
      "@skills": path("../skills"),
    },
    dedupe: ["react", "react-dom", "remotion"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id))
            return "react-runtime";
          if (/node_modules\/(remotion|@remotion)\//.test(id))
            return "remotion-player";
        },
      },
    },
  },
  server: {
    fs: { allow: [path("."), path("../motion"), path("../skills")] },
    proxy: { "/api": { target, timeout: 0 }, "/workspace": { target } },
  },
});
