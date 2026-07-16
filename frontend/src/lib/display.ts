export function displayBroker(value?: string | null): string {
  const normalized = (value ?? "TradeLocker").trim().toLowerCase();
  if (normalized === "herofx") return "HeroFX";
  if (normalized === "tradelocker") return "TradeLocker";
  return value?.trim() || "TradeLocker";
}

export function displayValue(value?: string | null): string {
  const labels: Record<string, string> = {
    read_only: "Read Only", demo_manual: "Demo Manual", demo_autonomous: "Demo Autonomous",
    hourly_forex: "Hourly Forex", hourly_forex_v1: "Hourly Forex v1",
    connected: "Connected", ready: "Ready", active: "Active", unavailable: "Unavailable",
    live: "Live", demo: "Demo", unknown: "Unknown", disabled: "Disabled",
  };
  const normalized = (value ?? "unknown").toLowerCase();
  return labels[normalized] ?? normalized.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
}

export function displayStrategy(name?: string | null, version?: string | null): string {
  if (name === "hourly_forex" && version === "1") return "Hourly Forex v1";
  return `${displayValue(name)}${version ? ` v${version}` : ""}`;
}
