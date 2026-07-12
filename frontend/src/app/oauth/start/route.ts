import { NextRequest, NextResponse } from "next/server";

import { ONBOARDING_COOKIE, onboardingCookieOptions } from "@/lib/onboarding-transaction";

export async function GET(request: NextRequest) {
  const transaction = request.nextUrl.searchParams.get("transaction");
  if (!transaction || transaction.length > 256) {
    return NextResponse.redirect(new URL("/setup-complete?onboardingError=invalid", request.url));
  }
  const response = NextResponse.redirect(new URL("/auth/login?returnTo=/onboarding/resume", request.url));
  response.cookies.set(ONBOARDING_COOKIE, transaction, onboardingCookieOptions());
  return response;
}
