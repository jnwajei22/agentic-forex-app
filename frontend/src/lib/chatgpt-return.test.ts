import assert from "node:assert/strict";
import test from "node:test";

import {
  accountSelectionPath,
  completedSetupPath,
  safeChatGptReturnTo,
} from "./chatgpt-return.ts";
import {
  afterAccountSelected,
  afterCredentialsSaved,
  isAllowedOAuthCallback,
} from "./onboarding-transaction.ts";
import { onboardingDestination, parseTradeLockerStatus } from "./tradelocker-status.ts";
import { onboardingHttpDisposition } from "./onboarding-http.ts";
import { signOnboardingAssertion } from "./onboarding-assertion.ts";

test("preserves an allowed returnTo through account selection and completion", () => {
  const returnTo = safeChatGptReturnTo("https://chatgpt.com");
  assert.equal(
    accountSelectionPath(returnTo),
    "/select-account?returnTo=https%3A%2F%2Fchatgpt.com",
  );
  assert.equal(
    completedSetupPath(returnTo),
    "/setup-complete?returnTo=https%3A%2F%2Fchatgpt.com",
  );
});

test("allows both ChatGPT origins", () => {
  assert.equal(safeChatGptReturnTo("https://chatgpt.com"), "https://chatgpt.com");
  assert.equal(safeChatGptReturnTo("https://chat.openai.com"), "https://chat.openai.com");
});

test("rejects unsafe returnTo values", () => {
  assert.equal(safeChatGptReturnTo("https://example.com"), null);
  assert.equal(safeChatGptReturnTo("javascript:alert(1)"), null);
  assert.equal(safeChatGptReturnTo("/dashboard"), null);
});

test("uses the dashboard after selection when returnTo is absent or unsafe", () => {
  assert.equal(completedSetupPath(null), "/dashboard?connected=1");
  assert.equal(
    completedSetupPath(safeChatGptReturnTo("https://example.com")),
    "/dashboard?connected=1",
  );
});

test("routes authenticated users to the first incomplete onboarding step", () => {
  assert.equal(onboardingDestination("not_connected"), "/connect-tradelocker");
  assert.equal(onboardingDestination("connected_no_account"), "/select-account");
  assert.equal(onboardingDestination("ready"), "/setup-complete");
  assert.equal(onboardingDestination("invalid_credentials"), "/connect-tradelocker?connectionIssue=invalid_credentials");
  assert.equal(onboardingDestination("expired"), "/connect-tradelocker?connectionIssue=expired");
  assert.equal(onboardingDestination("unavailable"), null);
});

test("malformed and unknown backend statuses become a safe unavailable state", () => {
  const missing = parseTradeLockerStatus({});
  assert.equal(missing.status, "unavailable");
  assert.equal(missing.safeRawStatus, "<missing>");
  assert.equal(missing.malformed, true);
  const unknown = parseTradeLockerStatus({ status: "legacy_surprise", connected: false });
  assert.equal(unknown.status, "unavailable");
  assert.equal(unknown.safeRawStatus, "legacy_surprise");
});

test("parses the documented current backend response shape", () => {
  const status = parseTradeLockerStatus({
    status: "ready", connected: true,
    selected_account: { account_id: "12345", account_number: "2", server: "DEMO" },
  });
  assert.equal(status.status, "ready");
  assert.equal(status.selected_account?.account_id, "12345");
});

test("normalizes temporary legacy TradeLocker response shapes", () => {
  assert.equal(parseTradeLockerStatus({ connected: false }).status, "not_connected");
  assert.equal(parseTradeLockerStatus({ connected: true, selected_account: null }).status, "connected_no_account");
  assert.equal(parseTradeLockerStatus({ connected: true, selected_account: { account_id: "1" } }).status, "ready");
  assert.equal(parseTradeLockerStatus({ connection_status: "not_connected", connected: false }).status, "not_connected");
  assert.equal(parseTradeLockerStatus({ connectionStatus: "ready", connected: true }).status, "ready");
});

test("does not normalize JSON error objects into connection states", () => {
  const parsed = parseTradeLockerStatus({ detail: "Not authenticated" });
  assert.equal(parsed.status, "unavailable");
  assert.equal(parsed.malformed, true);
});

test("classifies onboarding HTTP errors before status parsing", () => {
  assert.equal(onboardingHttpDisposition(401), "session_expired");
  assert.equal(onboardingHttpDisposition(403), "session_expired");
  assert.equal(onboardingHttpDisposition(404), "configuration_error");
  assert.equal(onboardingHttpDisposition(500), "unavailable");
  assert.equal(onboardingHttpDisposition(502), "unavailable");
});

test("Vercel server assertion binds Auth0 identity, transaction, audience, and expiry", () => {
  const token = signOnboardingAssertion({
    subject: "auth0|user-a", transaction: "opaque-reference", secret: "test-secret",
    issuer: "https://agentic-forex-app.vercel.app",
    audience: "https://mcp.justinnwajei.com/api/oauth/onboarding",
    issuedAt: 1_700_000_000, nonce: "single-use-nonce",
  });
  const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString()) as Record<string, unknown>;
  assert.equal(payload.sub, "auth0|user-a");
  assert.equal(payload.aud, "https://mcp.justinnwajei.com/api/oauth/onboarding");
  assert.equal(payload.exp, 1_700_000_060);
  assert.equal(payload.jti, "single-use-nonce");
  assert.equal(typeof payload.tx_hash, "string");
  assert.equal(token.includes("opaque-reference"), false);
});

test("only accepts exact approved OAuth callback origins", () => {
  assert.equal(isAllowedOAuthCallback("https://chatgpt.com/aip/callback?code=abc&state=state"), true);
  assert.equal(isAllowedOAuthCallback("https://chat.openai.com/aip/callback"), true);
  assert.equal(isAllowedOAuthCallback("https://chatgpt.com.evil.example/callback"), false);
  assert.equal(isAllowedOAuthCallback("javascript:alert(1)"), false);
});

test("local onboarding keeps the OAuth transaction flow after both TradeLocker steps", () => {
  assert.equal(afterCredentialsSaved(true, "/select-account"), "/onboarding");
  assert.equal(afterAccountSelected(true, "/dashboard"), "/onboarding");
});
