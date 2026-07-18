import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  BrowserBackendError,
  browserBackendFetch,
  browserBackendMutation,
  type AutonomousControls,
  updateAutonomousControls,
} from "./browser-backend.ts";

const controls: AutonomousControls = {
  global_autonomous_kill_switch: false,
  demo_autonomous_enabled: false,
  live_autonomous_enabled: false,
  live_execution_supported: false,
  updated_at: "2026-07-16T00:00:00Z",
  effective: { demo: "manual", live: "manual" },
};

test("browser GET and PATCH use the same authenticated backend proxy", { concurrency: false }, async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify(controls), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await browserBackendFetch("autonomous-controls");
    await browserBackendMutation("autonomous-controls", "PATCH", { demo_autonomous_enabled: true });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(calls.map(call => call.url), [
    "/api/backend/autonomous-controls",
    "/api/backend/autonomous-controls",
  ]);
  assert.equal(calls[1].init?.method, "PATCH");
  assert.equal(calls[1].init?.credentials, "same-origin");
  assert.equal(new Headers(calls[1].init?.headers).get("Content-Type"), "application/json");
  assert.notEqual(calls[1].url, "/api/autonomous-controls");
});

test("demo toggle sends the exact patch and commits only the server response", async () => {
  const serverControls = { ...controls, demo_autonomous_enabled: true, updated_at: "2026-07-16T01:00:00Z" };
  const commits: AutonomousControls[] = [];
  let requestArgs: unknown[] = [];
  const result = await updateAutonomousControls(controls, { demo_autonomous_enabled: true }, value => commits.push(value), async (...args) => {
    requestArgs = args;
    return serverControls;
  });

  assert.deepEqual(requestArgs, ["autonomous-controls", "PATCH", { demo_autonomous_enabled: true }]);
  assert.deepEqual(commits, [serverControls]);
  assert.equal(result.updated_at, serverControls.updated_at);
});

test("failed control PATCH restores the previous toggle state", async () => {
  const commits: AutonomousControls[] = [];
  await assert.rejects(
    updateAutonomousControls(controls, { demo_autonomous_enabled: true }, value => commits.push(value), async () => {
      throw new BrowserBackendError(503, "Autonomous controls are unavailable.");
    }),
    /Autonomous controls are unavailable/,
  );
  assert.deepEqual(commits, [controls]);
});

test("proxy supports PATCH and forwards GET and PATCH through configured backend helper", () => {
  const proxy = readFileSync(new URL("../app/api/backend/[...path]/route.ts", import.meta.url), "utf8");
  const dashboard = readFileSync(new URL("../app/dashboard/page.tsx", import.meta.url), "utf8");
  const backend = readFileSync(new URL("./backend.ts", import.meta.url), "utf8");
  const runtime = readFileSync(new URL("./backend-runtime.ts", import.meta.url), "utf8");

  assert.match(proxy, /"autonomous-controls"/);
  assert.match(proxy, /export async function PATCH/);
  assert.match(proxy, /backendFetch\(`\/api\/\$\{path\}\$\{request\.nextUrl\.search\}`/);
  assert.match(dashboard, /loadDashboardData\(await authenticatedBackendClient\(\)\)/);
  assert.match(readFileSync(new URL("./dashboard-data.ts", import.meta.url), "utf8"), /"\/api\/autonomous-controls"/);
  assert.match(runtime, /env\.NEXT_PUBLIC_API_BASE_URL/);
  assert.match(backend, /fetch\(`\$\{baseUrl\}\$\{path\}`/);
});

test("live enable payload requires the explicit confirmation phrase", () => {
  const dashboard = readFileSync(new URL("../app/dashboard/accounts-panel.tsx", import.meta.url), "utf8");
  assert.match(dashboard, /patchControls\(\{ live_autonomous_enabled: true, live_confirmation: dialog\.confirmation \}\)/);
  assert.match(dashboard, /dialog\.confirmation !== "ENABLE LIVE AUTONOMY"/);
  assert.doesNotMatch(dashboard, /reason: "Dashboard toggle"|reason: "Explicit live activation"/);
});
