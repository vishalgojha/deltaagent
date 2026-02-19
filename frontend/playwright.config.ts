import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true
  },
  webServer: [
    {
      command: "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir ..",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL: process.env.DATABASE_URL ?? "sqlite+aiosqlite:///./smoke.db",
        REDIS_URL: process.env.REDIS_URL ?? "redis://localhost:6379/0",
        JWT_SECRET: process.env.JWT_SECRET ?? "smoke_jwt_secret",
        ENCRYPTION_KEY: process.env.ENCRYPTION_KEY ?? "00000000000000000000000000000000",
        USE_MOCK_BROKER: process.env.USE_MOCK_BROKER ?? "true",
        AUTO_CREATE_TABLES: process.env.AUTO_CREATE_TABLES ?? "true",
        DECISION_BACKEND_DEFAULT: process.env.DECISION_BACKEND_DEFAULT ?? "deterministic",
        CORS_ORIGINS: process.env.CORS_ORIGINS ?? "[\"http://127.0.0.1:5173\"]"
      }
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
        VITE_WS_BASE_URL: process.env.VITE_WS_BASE_URL ?? "ws://127.0.0.1:8000"
      }
    }
  ]
});
