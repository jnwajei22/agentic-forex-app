export type StatusTone = "positive" | "info" | "selected" | "negative";

const LABELS: Record<string, string> = {
  read_only: "Read Only",
  demo_manual: "Demo Manual",
  demo_autonomous: "Demo Autonomous",
  kill_switch_enabled: "Kill Switch Enabled",
  reauthentication_required: "Reauthentication Required",
  unable_to_verify: "Unable to Verify",
  selected_account: "Selected Account",
  selected_connection: "Selected Connection",
};

const POSITIVE = new Set([
  "ready", "connected", "active", "enabled", "healthy", "confirmed",
  "available", "completed", "passed", "success",
]);
const SELECTED = new Set(["selected_account", "selected_connection", "pending", "armed"]);
const NEGATIVE = new Set([
  "unavailable", "unable_to_verify", "disconnected", "disabled", "error",
  "failed", "blocked", "expired", "reauthentication_required",
  "kill_switch_enabled", "not_connected",
]);

export function normalizeStatus(value?: string | null): string {
  return (value ?? "unknown").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

export function statusLabel(value?: string | null): string {
  const normalized = normalizeStatus(value);
  return LABELS[normalized]
    ?? normalized.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
}

export function statusTone(value?: string | null): StatusTone {
  const normalized = normalizeStatus(value);
  if (POSITIVE.has(normalized)) return "positive";
  if (SELECTED.has(normalized)) return "selected";
  if (NEGATIVE.has(normalized)) return "negative";
  return "info";
}
