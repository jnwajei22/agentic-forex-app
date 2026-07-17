import assert from "node:assert/strict";
import test from "node:test";

import { isValidRunTime, isValidTimeZone, nextLocalRunLabel, sortRunTimes, utcTimeForLocal, validateRunTimes } from "./schedule.ts";

test("validates HH:MM schedule rows and rejects empty or duplicate times", () => {
  assert.equal(isValidRunTime("05:00"), true);
  assert.equal(isValidRunTime("25:00"), false);
  assert.equal(validateRunTimes([]), "Add at least one run time.");
  assert.equal(validateRunTimes(["09:00", "09:00"]), "Run times must be unique.");
  assert.equal(validateRunTimes(["09:00", "13:15"]), null);
  assert.equal(isValidTimeZone("America/Chicago"), true);
  assert.equal(isValidTimeZone("Mars/Olympus"), false);
});

test("sorts schedule times before saving", () => {
  assert.deepEqual(sortRunTimes(["13:15", "05:00", "09:00"]), ["05:00", "09:00", "13:15"]);
});

test("previews America/Chicago times in UTC", () => {
  assert.equal(utcTimeForLocal("05:00", "America/Chicago", new Date("2026-07-16T12:00:00Z")), "10:00");
  assert.equal(nextLocalRunLabel(["05:00", "09:00"], "America/Chicago", new Date("2026-07-16T12:00:00Z")), "Today at 09:00");
});
