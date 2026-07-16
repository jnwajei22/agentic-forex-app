import test from "node:test";
import assert from "node:assert/strict";
import { displayBroker, displayStrategy, displayValue } from "./display.ts";

test("formats broker and internal values for people", () => {
  assert.equal(displayBroker("HEROFX"), "HeroFX");
  assert.equal(displayBroker("tradelocker"), "TradeLocker");
  assert.equal(displayValue("read_only"), "Read Only");
  assert.equal(displayValue("demo_manual"), "Demo Manual");
  assert.equal(displayStrategy("hourly_forex", "1"), "Hourly Forex v1");
});
