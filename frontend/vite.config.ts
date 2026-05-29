import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 后端默认从 8000 改为 8001（绕开 Windows TCP socket 泄漏在 8000 的幽灵 LISTENING）；
      // 用 127.0.0.1 而不是 localhost，避免 DNS / hosts 解析意外；
      // Node http 代理转发会读 $http_proxy，start-frontend.bat 已显式清空
      "/api": "http://127.0.0.1:8001",
      "/health": "http://127.0.0.1:8001",
      "/ws": { target: "ws://127.0.0.1:8001", ws: true },
    },
  },
});
