import assert from "node:assert/strict";
import test from "node:test";

import { classifyHttpStatus, classifyNetworkError, resolveBackendBaseUrl, safeBackendDiagnostic } from "./backend-runtime.ts";

test("production resolves the configured public backend and never its Vercel origin",()=>{
  const env={NODE_ENV:"production",NEXT_PUBLIC_API_BASE_URL:"https://api.agenticforexdesk.com/",APP_BASE_URL:"https://agentic-forex-app.vercel.app"};
  assert.equal(resolveBackendBaseUrl(env),"https://api.agenticforexdesk.com");
  assert.throws(()=>resolveBackendBaseUrl({...env,NEXT_PUBLIC_API_BASE_URL:env.APP_BASE_URL}),/backend_url_points_to_frontend/);
  assert.throws(()=>resolveBackendBaseUrl({...env,NEXT_PUBLIC_API_BASE_URL:"http://localhost:8000"}),/backend_url_localhost_in_production/);
});

test("safe diagnostics expose configuration and hostname but no URL credentials",()=>{
  const diagnostic=safeBackendDiagnostic("/api/broker/status","GET",{NEXT_PUBLIC_API_BASE_URL:"https://user:pass@api.example.test/private?secret=x",AUTH0_AUDIENCE:"configured",AUTH0_DOMAIN:"tenant.example"});
  assert.equal(diagnostic.backendHostname,"api.example.test");
  assert.equal(diagnostic.path,"/api/broker/status");
  assert.equal(JSON.stringify(diagnostic).includes("user"),false);
  assert.equal(JSON.stringify(diagnostic).includes("secret=x"),false);
});

test("401, 404, 500, timeout and DNS failures remain distinguishable",()=>{
  assert.equal(classifyHttpStatus(401),"unauthorized");assert.equal(classifyHttpStatus(404),"not_found");
  assert.equal(classifyHttpStatus(500),"server_error");
  assert.equal(classifyNetworkError({name:"TimeoutError"}),"timeout");
  assert.equal(classifyNetworkError({cause:{code:"ENOTFOUND"}}),"dns");
});
