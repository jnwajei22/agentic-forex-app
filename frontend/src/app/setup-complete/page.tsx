import { cookies } from "next/headers";
import Link from "next/link";

import { auth0 } from "@/lib/auth0";
import { BackendError, type BackendResponse } from "@/lib/backend";
import { onboardingBackendFetchWithMetadata } from "@/lib/onboarding-backend";
import { safeChatGptReturnTo } from "@/lib/chatgpt-return";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import { requireSession } from "@/lib/session";
import OnboardingShell from "@/components/onboarding-shell";
import { parseTradeLockerStatus } from "@/lib/tradelocker-status";

export default async function SetupCompletePage({ searchParams }: { searchParams: Promise<{ returnTo?: string; onboardingError?: string }> }) {
  const query = await searchParams;
  const returnTo = safeChatGptReturnTo(query.returnTo);
  await requireSession("/setup-complete");
  const session = await auth0.getSession();
  const transaction = (await cookies()).get(ONBOARDING_COOKIE)?.value;
  if (query.onboardingError === "owner") {
    return <OnboardingShell eyebrow="ChatGPT sign-in" title="Sign-in session belongs to another account">
      <p>This onboarding session is bound to a different authenticated account. Restart sign-in from ChatGPT with the intended account.</p>
    </OnboardingShell>;
  }
  if (["expired", "invalid"].includes(query.onboardingError ?? "") || !transaction) {
    return <OnboardingShell eyebrow="ChatGPT sign-in" title="Restart sign-in from ChatGPT">
      <p>This sign-in session is missing or has expired. Restart sign-in from ChatGPT.</p>
    </OnboardingShell>;
  }
  if (query.onboardingError === "configuration") {
    return <OnboardingShell eyebrow="Configuration error" title="Onboarding endpoint unavailable">
      <p>The backend onboarding endpoint is not configured correctly.</p>
    </OnboardingShell>;
  }
  if (query.onboardingError === "unavailable") {
    return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
      <p>The onboarding service is temporarily unavailable. Try again shortly.</p>
      <div className="actions"><Link className="button" href="/setup-complete">Try again</Link></div>
    </OnboardingShell>;
  }

  let response: BackendResponse<unknown>;
  try {
    response = await onboardingBackendFetchWithMetadata<unknown>(
      "/api/oauth/onboarding/status", transaction,
      { method: "POST", body: JSON.stringify({ transaction }) },
    );
  } catch (error) {
    if (error instanceof BackendError) {
      const backendCode = typeof error.payload?.error === "string" ? error.payload.error : undefined;
      if (error.status === 403 && backendCode === "onboarding_owner_mismatch") {
        return <OnboardingShell eyebrow="ChatGPT sign-in" title="Sign-in session belongs to another account">
          <p>This onboarding session is bound to a different authenticated account. Restart sign-in from ChatGPT with the intended account.</p>
        </OnboardingShell>;
      }
      if (error.status === 401 || error.status === 410) {
        return <OnboardingShell eyebrow="ChatGPT sign-in" title="Restart sign-in from ChatGPT">
          <p>This sign-in session is missing or has expired. Restart sign-in from ChatGPT.</p>
        </OnboardingShell>;
      }
    }
    return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
      <p>The onboarding service is temporarily unavailable. Try again shortly.</p>
      <div className="actions"><Link className="button" href="/setup-complete">Try again</Link></div>
    </OnboardingShell>;
  }
  const status = parseTradeLockerStatus(response.data);
  if (status.malformed) {
    console.error("[setup-complete] Malformed successful TradeLocker status", {
      endpoint: response.endpoint,
      httpStatus: response.status,
      contentType: response.contentType,
      payloadKeys: response.data && typeof response.data === "object" ? Object.keys(response.data) : [],
      normalizedStatus: status.status,
      requestId: response.requestId,
    });
    return <OnboardingShell eyebrow="Connection status" title="Unable to check TradeLocker">
      <p>The onboarding service returned an unexpected response. Try again shortly.</p>
    </OnboardingShell>;
  }
  const transactionReady = Boolean(session && status.csrf_token);
  const setupReady = status.status === "ready" && status.selected_account;

  if (!transactionReady) {
    return <OnboardingShell eyebrow="ChatGPT sign-in" title="Restart sign-in from ChatGPT">
      <p>This sign-in session is missing or has expired. Restart sign-in from ChatGPT.</p>
      {returnTo && <div className="actions"><Link className="button" href={returnTo}>Return to ChatGPT</Link></div>}
    </OnboardingShell>;
  }

  if (!setupReady) {
    return <OnboardingShell eyebrow="TradeLocker setup" title="Setup is not complete">
      <p>Connect TradeLocker and select a TradeLocker account before continuing.</p>
      <div className="actions"><Link className="button" href="/onboarding">Continue setup</Link></div>
    </OnboardingShell>;
  }

  return <OnboardingShell eyebrow="Setup complete" title="Agentic Forex Desk is connected">
    <p>Your selected TradeLocker account is ready.</p>
    <div className="card">
      <div className="label">TradeLocker server</div><div className="value">{status.selected_account?.server}</div>
      <div className="label" style={{ marginTop: 18 }}>TradeLocker account</div><div className="value">{status.selected_account?.account_id} · {status.selected_account?.account_number}</div>
    </div>
    <form className="actions" action="/oauth/complete" method="post">
      <input type="hidden" name="csrfToken" value={status.csrf_token} />
      <button className="button" type="submit">Use with ChatGPT</button>
    </form>
  </OnboardingShell>;
}
