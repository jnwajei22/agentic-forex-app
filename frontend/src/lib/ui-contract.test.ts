import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("dashboard navigation and direct route use /dashboard", () => {
  const navigation = source("../app/navigation.tsx");
  const dashboard = source("../app/dashboard/page.tsx");
  assert.match(navigation, /href="\/dashboard"/);
  assert.match(dashboard, /Backend API Unavailable/);
  assert.doesNotMatch(dashboard, /redirect\(.*\/\)/);
});

test("offline dashboard remains visible without claiming an empty database", () => {
  const dashboard = source("../app/dashboard/page.tsx");
  const accounts = source("../app/dashboard/accounts-panel.tsx");
  assert.match(dashboard, /loadState === "unavailable"/);
  assert.match(dashboard, /Unable to Verify/);
  assert.match(dashboard, /Restore Backend Connection/);
  assert.match(accounts, /if \(loadState === "unavailable"\)/);
  assert.match(accounts, /if \(!connections\.length && !sectionErrors\.connections\)/);
  assert.ok(accounts.indexOf('loadState === "unavailable"') < accounts.indexOf("!connections.length"));
});

test("dashboard uses selected language and keeps credentials in Settings", () => {
  const dashboard = source("../app/dashboard/page.tsx");
  const accounts = source("../app/dashboard/accounts-panel.tsx");
  const settings = source("../app/settings/panel.tsx");
  assert.match(dashboard, /Selected TradeLocker Account/);
  assert.doesNotMatch(`${dashboard}${accounts}`, /Default Account|Default Connection|Update Credentials/);
  assert.match(settings, /TradeLocker Connections/);
  assert.match(settings, /Update Credentials/);
  assert.match(settings, /Add Connection/);
  assert.match(settings, /Disable Connection/);
});

test("connection headers omit account-level environment and selected pills", () => {
  const accounts = source("../app/dashboard/accounts-panel.tsx");
  const header = accounts.slice(accounts.indexOf('<header className="connection-header"'), accounts.indexOf('<div className="metadata">'));
  assert.doesNotMatch(header, /connection\.environment|selected_connection/);
  assert.match(accounts, /account\.is_demo/);
  assert.match(accounts, /selected_account/);
});

test("dashboard workflows use accessible application dialogs instead of browser dialogs", () => {
  const accounts = source("../app/dashboard/accounts-panel.tsx");
  const settings = source("../app/settings/panel.tsx");
  const modal = source("../components/app-modal.tsx");
  const schedule = source("../components/schedule-modal.tsx");
  assert.doesNotMatch(`${accounts}${settings}`, /window\.(?:prompt|confirm|alert)/);
  assert.match(modal, /role="dialog"/);
  assert.match(modal, /aria-modal="true"/);
  assert.match(modal, /event\.key === "Escape"/);
  assert.match(schedule, /Schedule Autonomous Runs/);
  assert.match(schedule, /Add Time/);
  assert.match(schedule, /Save Schedule/);
});

test("shared blue, money-green, gold, and danger tokens are present", () => {
  const css = source("../app/globals.css");
  assert.match(css, /--blue: #155eef/i);
  assert.match(css, /--money-green: #168b54/i);
  assert.match(css, /--gold: #d4a72c/i);
  assert.match(css, /--danger: #d92d20/i);
  assert.match(css, /\.status-positive/);
  assert.match(css, /\.status-selected/);
  assert.match(css, /\.status-negative/);
});
