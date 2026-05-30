import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import fs from "node:fs";

/**
 * 动态后端端口：
 * - scripts/start_backend.ps1 启动时会在 `.dev-port` 写入当前选定的端口号
 * - 后端在 Windows 上踩 tcpip.sys socket 泄漏时会自动跳到下一个端口
 * - 这里启动时读一次；如果文件不存在，fallback 到 8001
 *
 * 想锁定端口：设 BACKEND_PORT 环境变量，例如 `BACKEND_PORT=8000 pnpm dev`。
 */
function readBackendPort(): number {
  const envPort = Number(process.env.BACKEND_PORT);
  if (Number.isFinite(envPort) && envPort > 0) return envPort;
  const portFile = path.resolve(__dirname, ".dev-port");
  try {
    const content = fs.readFileSync(portFile, "utf-8").trim();
    const port = Number(content);
    if (Number.isFinite(port) && port > 0) return port;
  } catch {
    // 文件不存在或读取失败，用 fallback
  }
  return 8000;
}

const BACKEND_PORT = readBackendPort();
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const BACKEND_WS = `ws://127.0.0.1:${BACKEND_PORT}`;

// eslint-disable-next-line no-console
console.log(`[vite] backend → ${BACKEND_URL}`);

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
      "/api": BACKEND_URL,
      "/health": BACKEND_URL,
      "/ws": { target: BACKEND_WS, ws: true },
    },
  },
});
