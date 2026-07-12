import { requireSession } from "@/lib/session";
import AccountSelector from "./selector";
import { safeChatGptReturnTo, withReturnTo } from "@/lib/chatgpt-return";
import { cookies } from "next/headers";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import OnboardingShell from "@/components/onboarding-shell";

export default async function SelectAccountPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const returnTo = safeChatGptReturnTo((await searchParams).returnTo);
  const session = await requireSession(withReturnTo("/select-account", returnTo));
  const onboarding = Boolean((await cookies()).get(ONBOARDING_COOKIE)?.value && session.user.sub);
  return <OnboardingShell eyebrow="TradeLocker setup" title="Select TradeLocker account">
    <p>Choose the TradeLocker account for this connection.</p>
    <AccountSelector returnTo={returnTo} onboarding={onboarding} />
  </OnboardingShell>;
}
