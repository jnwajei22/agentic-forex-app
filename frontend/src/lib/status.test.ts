import assert from "node:assert/strict";
import test from "node:test";

import { statusLabel, statusTone } from "./status.ts";

test("formats internal status values in title case", () => {
  assert.equal(statusLabel("ready"), "Ready");
  assert.equal(statusLabel("read_only"), "Read Only");
  assert.equal(statusLabel("demo_autonomous"), "Demo Autonomous");
  assert.equal(statusLabel("kill_switch_enabled"), "Kill Switch Enabled");
  assert.equal(statusLabel("reauthentication_required"), "Reauthentication Required");
});

test("maps positive, neutral, selected, and negative states semantically", () => {
  for (const value of ["ready", "connected", "active"]) assert.equal(statusTone(value), "positive");
  assert.equal(statusTone("demo"), "info");
  assert.equal(statusTone("selected_account"), "selected");
  for (const value of ["unavailable", "disabled", "kill_switch_enabled"]) {
    assert.equal(statusTone(value), "negative");
  }
});
