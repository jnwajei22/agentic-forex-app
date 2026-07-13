import { NextRequest, NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { onboardingBackendFetch } from "@/lib/onboarding-backend";
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
  } catch {
    return NextResponse.redirect(new URL("/setup-complete?onboardingError=owner", request.url));
  }
  return NextResponse.redirect(new URL("/onboarding", request.url));
}
