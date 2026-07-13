export type ConnectionAlert = {
  kind: "error";
  message: string;
} | null;

export function getConnectionAlert({
  connectionIssue,
  reconnectRequired,
  hasStoredConnection,
}: {
  connectionIssue?: string | null;
  reconnectRequired: boolean;
  hasStoredConnection: boolean;
}): ConnectionAlert {
  if (connectionIssue === "invalid_credentials") {
    return {
      kind: "error",
      message: "TradeLocker rejected the credentials or server selection. Confirm the trading credentials, exact server code, and environment.",
    };
  }
  if (connectionIssue === "upstream_unavailable") {
    return {
      kind: "error",
      message: "TradeLocker is temporarily unavailable. Try again shortly.",
    };
  }
  if (reconnectRequired && hasStoredConnection) {
    return {
      kind: "error",
      message: "Reconnect your TradeLocker credentials to continue.",
    };
  }
  return null;
}
