import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_PROXY_API ?? "http://localhost:8000", changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("@mui/x-charts")) return "charts";
          if (id.includes("@mui") || id.includes("@emotion")) return "mui";
          if (id.includes("node_modules")) return "vendor";
        },
      },
    },
  },
});
