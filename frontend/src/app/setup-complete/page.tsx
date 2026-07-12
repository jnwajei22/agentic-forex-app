import { cookies } from "next/headers";
import Link from "next/link";

import { auth0 } from "@/lib/auth0";
import { backendFetch } from "@/lib/backend";
import { safeChatGptReturnTo } from "@/lib/chatgpt-return";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";
import { requireSession } from "@/lib/session";
import OnboardingShell from "@/components/onboarding-shell";

type Status = {
  status: string;
  server?: string;
  accountId?: string;
  accNum?: string;
  csrf_token?: string;
};

export default async function SetupCompletePage({ searchParams }: { searchParams: Promise<{ returnTo?: string; onboardingError?: string }> }) {
  const query = await searchParams;
  const returnTo = safeChatGptReturnTo(query.returnTo);
  await requireSession("/setup-complete");
  const session = await auth0.getSession();
  const transaction = (await cookies()).get(ONBOARDING_COOKIE)?.value;
  let status: Status = { status: "invalid" };
  if (transaction && session) {
    try {
      status = await backendFetch<Status>("/api/oauth/onboarding/status", {
        method: "POST", body: JSON.stringify({ transaction }),
      });
    } catch { /* Render the restart state below. */ }
  }
  const transactionReady = Boolean(transaction && session && status.csrf_token);
  const setupReady = status.status === "connected" && status.accountId && status.accNum;

  if (query.onboardingError || !transactionReady) {
    return <OnboardingShell eyebrow="ChatGPT sign-in" title="Restart sign-in from ChatGPT">
      <p>The ChatGPT authorization request is missing, expired, or does not belong to this account.</p>
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
      <div className="label">TradeLocker server</div><div className="value">{status.server}</div>
      <div className="label" style={{ marginTop: 18 }}>TradeLocker account</div><div className="value">{status.accountId} · {status.accNum}</div>
    </div>
    <form className="actions" action="/oauth/complete" method="post">
      <input type="hidden" name="csrfToken" value={status.csrf_token} />
      <button className="button" type="submit">Use with ChatGPT</button>
    </form>
  </OnboardingShell>;
}
