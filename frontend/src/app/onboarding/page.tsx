import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendFetch } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import { onboardingDestination, parseTradeLockerStatus } from "@/lib/tradelocker-status";
import { BackendError } from "@/lib/backend";
import OnboardingShell from "@/components/onboarding-shell";
import Link from "next/link";

export default async function OnboardingPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/onboarding/resume");
  const transaction = (await cookies()).get(ONBOARDING_COOKIE)?.value;
  if (!transaction) redirect("/setup-complete?onboardingError=expired");
  let response: unknown;
  try {
    response = await backendFetch<unknown>("/api/oauth/onboarding/status", {
      method: "POST", body: JSON.stringify({ transaction }),
    });
  } catch (error) {
    if (error instanceof BackendError && error.status === 410) {
      redirect("/setup-complete?onboardingError=expired");
    }
    if (error instanceof BackendError && error.status === 403) {
      redirect("/setup-complete?onboardingError=owner");
    }
    return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
      <p>The connection status service is temporarily unavailable. Try again shortly.</p>
      <div className="actions"><Link className="button" href="/onboarding">Try again</Link></div>
    </OnboardingShell>;
  }
  const status = parseTradeLockerStatus(response);
  if (status.malformed) {
    console.error("[onboarding] Malformed TradeLocker status", { status: status.safeRawStatus });
  }
  const destination = onboardingDestination(status.status);
  if (destination) redirect(destination);
  return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
    <p>{status.message ?? "The connection status service is temporarily unavailable."}</p>
    <div className="actions"><Link className="button" href="/onboarding">Try again</Link></div>
  </OnboardingShell>;
}
