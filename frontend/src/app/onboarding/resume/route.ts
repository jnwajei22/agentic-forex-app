import { NextRequest, NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { onboardingBackendFetch } from "@/lib/onboarding-backend";
import { BackendError } from "@/lib/backend";
import { safeIdentityFingerprint } from "@/lib/onboarding-assertion";
import { onboardingBindDisposition } from "@/lib/onboarding-http";
import { ONBOARDING_COOKIE } from "@/lib/onboarding-transaction";

export async function GET(request: NextRequest) {
  const session = await auth0.getSession();
  if (!session) return NextResponse.redirect(new URL("/auth/login?returnTo=/onboarding/resume", request.url));
  const transaction = request.cookies.get(ONBOARDING_COOKIE)?.value;
  if (!transaction) return NextResponse.redirect(new URL("/setup-complete?onboardingError=expired", request.url));
  try {
    await onboardingBackendFetch("/api/oauth/onboarding/bind", transaction, {
      method: "POST", body: JSON.stringify({ transaction }),
    });
  } catch (error) {
    if (error instanceof BackendError) {
      const backendCode = typeof error.payload?.error === "string" ? error.payload.error : undefined;
      console.error("[onboarding/resume] Bind failed", {
        httpStatus: error.status,
        backendCode,
        subjectFp: safeIdentityFingerprint(String(session.user.sub)),
        transactionFp: safeIdentityFingerprint(transaction),
        payloadKeys: Object.keys(error.payload ?? {}),
        requestId: typeof error.payload?.request_id === "string" ? error.payload.request_id : undefined,
      });
      const disposition = onboardingBindDisposition(error.status, backendCode);
      return NextResponse.redirect(new URL(`/setup-complete?onboardingError=${disposition}`, request.url));
    }
    return NextResponse.redirect(new URL("/setup-complete?onboardingError=unavailable", request.url));
  }
  return NextResponse.redirect(new URL("/onboarding", request.url));
}
