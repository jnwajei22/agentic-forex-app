import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendFetchWithMetadata } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import { onboardingDestination, parseTradeLockerStatus } from "@/lib/tradelocker-status";
import { BackendError, type BackendResponse } from "@/lib/backend";
import OnboardingShell from "@/components/onboarding-shell";
import Link from "next/link";
import { onboardingHttpDisposition } from "@/lib/onboarding-http";

export default async function OnboardingPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/onboarding/resume");
  const transaction = (await cookies()).get(ONBOARDING_COOKIE)?.value;
  if (!transaction) {
    return <OnboardingShell eyebrow="ChatGPT sign-in" title="Sign-in session expired">
      <p>This sign-in session is missing or has expired. Restart sign-in from ChatGPT.</p>
    </OnboardingShell>;
  }
  let response: BackendResponse<unknown>;
  try {
    response = await backendFetchWithMetadata<unknown>("/api/oauth/onboarding/status", {
      method: "POST", body: JSON.stringify({ transaction }),
    });
  } catch (error) {
    if (error instanceof BackendError) {
      console.error("[onboarding] Backend status request failed", {
        endpoint: error.endpoint ?? "/api/oauth/onboarding/status",
        httpStatus: error.status,
        contentType: error.contentType ?? "<missing>",
        payloadKeys: Object.keys(error.payload ?? {}),
        requestId: typeof error.payload?.request_id === "string" ? error.payload.request_id : undefined,
      });
      const disposition = onboardingHttpDisposition(error.status);
      if (disposition === "session_expired") {
        return <OnboardingShell eyebrow="ChatGPT sign-in" title="Sign-in session expired">
          <p>This sign-in session is missing or has expired. Restart sign-in from ChatGPT.</p>
        </OnboardingShell>;
      }
      if (disposition === "configuration_error") {
        return <OnboardingShell eyebrow="Configuration error" title="Onboarding endpoint unavailable">
          <p>The configured backend does not provide the onboarding status endpoint.</p>
        </OnboardingShell>;
      }
    }
    return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
      <p>The connection status service is temporarily unavailable. Try again shortly.</p>
      <div className="actions"><Link className="button" href="/onboarding">Try again</Link></div>
    </OnboardingShell>;
  }
  const status = parseTradeLockerStatus(response.data);
  if (status.malformed) {
    console.error("[onboarding] Malformed TradeLocker status", {
      endpoint: response.endpoint,
      httpStatus: response.status,
      contentType: response.contentType,
      payloadKeys: response.data && typeof response.data === "object" ? Object.keys(response.data) : [],
      normalizedStatus: status.status,
      rawStatus: status.safeRawStatus,
      requestId: response.requestId,
    });
  }
  const destination = onboardingDestination(status.status);
  if (destination) redirect(destination);
  return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
    <p>{status.message ?? "The connection status service is temporarily unavailable."}</p>
    <div className="actions"><Link className="button" href="/onboarding">Try again</Link></div>
  </OnboardingShell>;
}
