import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Browser end-to-end tests: the real UI against the real API, with the model replaced by the
// scripted FakeModelProvider of backend/tests/e2e_server.py (test database, DEBUG_MODE on).
const API_PORT = 8001;
const UI_PORT = 5174;
// the full Frostbridge slice script runs on its own API + UI pair (one fake script per process)
const FB_API_PORT = 8002;
const FB_UI_PORT = 5175;
const PY_SERVER = `${path.join(".venv", "Scripts", "python.exe")} -m tests.e2e_server`; // in ../backend

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${UI_PORT}`, trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop",
      testIgnore: /frostbridge/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    { name: "phone", testIgnore: /frostbridge/, use: { ...devices["Pixel 7"] } },
    {
      name: "frostbridge",
      testMatch: /frostbridge/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        baseURL: `http://127.0.0.1:${FB_UI_PORT}`,
      },
    },
  ],
  webServer: [
    {
      command: PY_SERVER,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${UI_PORT} --strictPort`,
      env: { VITE_API_TARGET: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${UI_PORT}`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: PY_SERVER,
      cwd: "../backend",
      env: { E2E_FIXTURE: "frostbridge", E2E_PORT: String(FB_API_PORT) },
      url: `http://127.0.0.1:${FB_API_PORT}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${FB_UI_PORT} --strictPort`,
      env: { VITE_API_TARGET: `http://127.0.0.1:${FB_API_PORT}` },
      url: `http://127.0.0.1:${FB_UI_PORT}`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
