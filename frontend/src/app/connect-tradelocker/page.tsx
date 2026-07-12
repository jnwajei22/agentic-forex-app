import { requireSession } from "@/lib/session";
import ConnectTradeLockerForm from "./form";
import { safeChatGptReturnTo, withReturnTo } from "@/lib/chatgpt-return";
import { cookies } from "next/headers";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import OnboardingShell from "@/components/onboarding-shell";

export default async function ConnectTradeLockerPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const returnTo = safeChatGptReturnTo((await searchParams).returnTo);
  const session = await requireSession(withReturnTo("/connect-tradelocker", returnTo));
  const onboarding = Boolean((await cookies()).get(ONBOARDING_COOKIE)?.value && session.user.sub);
  return <OnboardingShell eyebrow="TradeLocker setup" title="Connect TradeLocker">
    <p>Enter your TradeLocker credentials. These are separate from your portal login.</p>
    <p>Credentials are sent securely to the MCP server and are never stored in browser storage.</p>
    <ConnectTradeLockerForm returnTo={returnTo} onboarding={onboarding} />
  </OnboardingShell>;
}
