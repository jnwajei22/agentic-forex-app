import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/dashboard/accounts-panel.tsx", import.meta.url), "utf8");

test("dashboard exposes the simplified autonomous controls", () => {
  for (const label of ["Autonomous Trading", "Global Autonomous Kill Switch", "Demo Autonomous Trading", "Live Autonomous Trading"]) {
    assert.match(source, new RegExp(label));
  }
  assert.doesNotMatch(source, /Arm Demo Autonomy|Armed Until|Shadow Mode|execution-mode/);
  assert.match(source, /ENABLE LIVE AUTONOMY/);
  assert.match(source, /Live execution path not yet available/);
});

test("profile card primary actions are simplified and danger actions remain in edit", () => {
  const profileActions = source.match(/className="actions compact profile-actions">([\s\S]*?)<\/div><\/div>;/)?.[1] ?? "";
  assert.match(profileActions, /Check Status/);
  assert.match(profileActions, />Schedule</);
  assert.match(profileActions, /Edit Profile/);
  assert.doesNotMatch(profileActions, /Disable Profile|Delete Profile/);
  assert.match(source, /Danger Zone/);
  assert.match(source, /Disable Profile/);
  assert.match(source, /Delete Profile/);
  assert.match(source, /true, dialog\.profile\.name/);
});
