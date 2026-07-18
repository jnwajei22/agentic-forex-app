import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/dashboard/accounts-panel.tsx", import.meta.url), "utf8");

test("dashboard exposes safety-first autonomous controls", () => {
  for (const label of ["Automation control center", "Global kill switch", "Demo automation", "Live automation"]) {
    assert.match(source, new RegExp(label));
  }
  assert.doesNotMatch(source, /Arm Demo Autonomy|Armed Until|Shadow Mode|execution-mode/);
  assert.match(source, /ENABLE LIVE AUTONOMY/);
  assert.match(source, /Live execution is not supported/);
});

test("profile rows keep verification, editing, and protected destructive actions", () => {
  assert.match(source, />Verify</);
  assert.match(source, />Edit</);
  assert.match(source, /Danger zone/);
  assert.match(source, /Disable profile/);
  assert.match(source, /Delete profile/);
  assert.match(source, /confirmation_name=/);
});

test("normal profile editing does not expose server-side decision configuration", () => {
  assert.doesNotMatch(source, /Decision Engine|Decision Provider|Model Not Selected|Minimum Confidence|No Trade — Testing Only/);
  assert.doesNotMatch(source, /model_identifier|minimum_confidence|decision_provider: dialog\.draft/);
});
