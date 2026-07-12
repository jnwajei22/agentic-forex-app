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
  onboardingDestination,
} from "./onboarding-transaction.ts";

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
  assert.equal(onboardingDestination("setup_required"), "/connect-tradelocker");
  assert.equal(onboardingDestination("account_selection_required"), "/select-account");
  assert.equal(onboardingDestination("connected"), "/setup-complete");
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
