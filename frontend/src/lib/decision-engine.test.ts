import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { displayedProviderReadiness, validateMinimumConfidence } from "./decision-engine.ts";

test("minimum confidence accepts zero through one and rejects invalid values", () => {
  assert.equal(validateMinimumConfidence("0"), null);
  assert.equal(validateMinimumConfidence("0.7"), null);
  assert.equal(validateMinimumConfidence(1), null);
  assert.match(validateMinimumConfidence(1.01) ?? "", /between 0 and 1/);
  assert.match(validateMinimumConfidence("") ?? "", /between 0 and 1/);
});

test("provider readiness displays every supported safe state", () => {
  assert.equal(displayedProviderReadiness("no_trade", "", undefined).label, "Testing Only");
  assert.equal(displayedProviderReadiness("openai", "gpt-model", {
    status: "api_key_missing", label: "API Key Missing", ready: false,
    blocking_reasons: ["openai_api_key_missing"], api_key_configured: false, provider_available: true,
  }).label, "API Key Missing");
  assert.equal(displayedProviderReadiness("openai", "", {
    status: "ready", label: "Ready", ready: true, blocking_reasons: [],
    api_key_configured: true, provider_available: true,
  }).label, "Model Not Selected");
  assert.equal(displayedProviderReadiness("openai", "gpt-model", {
    status: "ready", label: "Ready", ready: true, blocking_reasons: [],
    api_key_configured: true, provider_available: true,
  }).label, "Ready");
  assert.equal(displayedProviderReadiness("openai", "gpt-model", {
    status: "provider_unavailable", label: "Provider Unavailable", ready: false,
    blocking_reasons: ["provider_unavailable"], api_key_configured: true, provider_available: false,
  }).label, "Provider Unavailable");
});

test("Edit Profile exposes and persists the stored Decision Engine fields", () => {
  const source = readFileSync(new URL("../app/dashboard/accounts-panel.tsx", import.meta.url), "utf8");
  assert.match(source, />Decision Engine</);
  assert.match(source, /profile\.decision_provider \|\| "no_trade"/);
  assert.match(source, /profile\.model_identifier \|\| ""/);
  assert.match(source, /profile\.minimum_confidence \?\? \.7/);
  assert.match(source, /<option value="openai">OpenAI<\/option>/);
  assert.match(source, /<option value="no_trade">No Trade — Testing Only<\/option>/);
  assert.match(source, /decision_provider: dialog\.draft\.decisionProvider/);
  assert.match(source, /model_identifier: dialog\.draft\.modelIdentifier/);
  assert.match(source, /minimum_confidence: Number\(dialog\.draft\.minimumConfidence\)/);
  assert.match(source, /This testing provider always records a no-trade decision and will never submit an order\./);
  assert.doesNotMatch(source, /OpenAI API Key|openai_api_key/);
});
