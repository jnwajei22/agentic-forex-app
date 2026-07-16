import { requireSession } from "@/lib/session";
import ConnectTradeLockerForm from "./form";
import { safeChatGptReturnTo, withReturnTo } from "@/lib/chatgpt-return";
import { cookies } from "next/headers";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import OnboardingShell from "@/components/onboarding-shell";
import { getConnectionAlert } from "@/lib/connection-alert";

export default async function ConnectTradeLockerPage({ searchParams }: { searchParams: Promise<{ returnTo?: string; connectionIssue?: string; reconnect_required?: string; connection_id?: string; new?: string }> }) {
  const query = await searchParams;
  const returnTo = safeChatGptReturnTo(query.returnTo);
  const session = await requireSession(withReturnTo("/connect-tradelocker", returnTo));
  const onboarding = Boolean((await cookies()).get(ONBOARDING_COOKIE)?.value && session.user.sub);
  const reconnectRequired = query.reconnect_required === "1"
    || query.connectionIssue === "reconnect_required"
    || query.connectionIssue === "expired";
  const initialAlert = getConnectionAlert({
    connectionIssue: query.connectionIssue,
    reconnectRequired,
    hasStoredConnection: reconnectRequired,
  });
  return <OnboardingShell eyebrow="TradeLocker setup" title="Connect TradeLocker">
    <p>Enter your TradeLocker credentials. These are separate from your portal login.</p>
    <p>Credentials are sent securely to the MCP server and are never stored in browser storage.</p>
    <ConnectTradeLockerForm returnTo={returnTo} onboarding={onboarding} initialAlert={initialAlert} connectionId={query.connection_id ?? null} createNew={query.new === "1"} />
  </OnboardingShell>;
}
