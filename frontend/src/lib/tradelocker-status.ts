export const TRADELOCKER_STATUSES = [
  "not_connected",
  "connected_no_account",
  "ready",
  "invalid_credentials",
  "expired",
  "unavailable",
] as const;

export type TradeLockerStatusValue = typeof TRADELOCKER_STATUSES[number];

export type TradeLockerStatus = {
  status: TradeLockerStatusValue;
  connected: boolean;
  selected_account: {
    account_id: string;
    account_number: string;
    account_alias?: string;
    server: string;
    environment?: "demo" | "live" | null;
  } | null;
  message?: string | null;
  retryable?: boolean;
  malformed?: boolean;
  safeRawStatus?: string;
  csrf_token?: string;
  transaction_valid?: boolean;
};

const knownStatuses = new Set<string>(TRADELOCKER_STATUSES);

export function parseTradeLockerStatus(value: unknown): TradeLockerStatus {
  const body = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidate = body.status ?? body.connection_status ?? body.connectionStatus;
  let rawStatus = typeof candidate === "string" ? candidate : undefined;
  const selectedValue = body.selected_account ?? body.selectedAccount;
  if (!rawStatus && typeof body.connected === "boolean") {
    rawStatus = body.connected
      ? (selectedValue ? "ready" : "connected_no_account")
      : "not_connected";
  }
  if (rawStatus === "setup_required") rawStatus = "not_connected";
  if (rawStatus === "account_selection_required") rawStatus = "connected_no_account";
  if (rawStatus === "connected") {
    rawStatus = selectedValue || body.accountId ? "ready" : "connected_no_account";
  }
  if (!rawStatus || !knownStatuses.has(rawStatus)) {
    return {
      status: "unavailable",
      connected: false,
      selected_account: null,
      message: "TradeLocker connection status is temporarily unavailable.",
      retryable: true,
      malformed: true,
      safeRawStatus: rawStatus?.slice(0, 80) ?? "<missing>",
    };
  }
  const selected = selectedValue;
  const selectedAccount = selected && typeof selected === "object"
    ? selected as TradeLockerStatus["selected_account"]
    : null;
  return {
    status: rawStatus as TradeLockerStatusValue,
    connected: body.connected === true,
    selected_account: selectedAccount,
    message: typeof body.message === "string" ? body.message : null,
    retryable: body.retryable === true,
    csrf_token: typeof body.csrf_token === "string" ? body.csrf_token : undefined,
    transaction_valid: body.transaction_valid === true,
  };
}

export function onboardingDestination(status: TradeLockerStatusValue): string | null {
  if (status === "not_connected") return "/connect-tradelocker";
  if (status === "connected_no_account") return "/select-account";
  if (status === "ready") return "/setup-complete";
  if (status === "invalid_credentials" || status === "expired") {
    return `/connect-tradelocker?connectionIssue=${status}`;
  }
  return null;
}
