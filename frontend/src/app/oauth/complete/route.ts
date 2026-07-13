import { NextRequest, NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { onboardingBackendFetch } from "@/lib/onboarding-backend";
import {
  isAllowedOAuthCallback,
  ONBOARDING_COOKIE,
} from "@/lib/onboarding-transaction";

export async function POST(request: NextRequest) {
  const session = await auth0.getSession();
  if (!session) return NextResponse.json({ error: "Authentication is required." }, { status: 401 });
  const transaction = request.cookies.get(ONBOARDING_COOKIE)?.value;
  if (!transaction) return NextResponse.json({ error: "The ChatGPT sign-in request expired. Restart sign-in from ChatGPT." }, { status: 400 });
  const form = await request.formData();
  const result = await onboardingBackendFetch<{ redirect_url: string }>("/api/oauth/onboarding/complete", transaction, {
    method: "POST",
    body: JSON.stringify({ transaction, csrf_token: String(form.get("csrfToken") ?? "") }),
  });
  if (!isAllowedOAuthCallback(result.redirect_url)) {
    return NextResponse.json({ error: "Invalid OAuth callback." }, { status: 502 });
  }
  const response = NextResponse.redirect(result.redirect_url, 303);
  response.cookies.delete(ONBOARDING_COOKIE);
  return response;
}
