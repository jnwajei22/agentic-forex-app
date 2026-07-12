import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendFetch } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { ONBOARDING_COOKIE, onboardingDestination } from "@/lib/onboarding-transaction";

type Status = { status: "setup_required" | "account_selection_required" | "connected" };

export default async function OnboardingPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/onboarding/resume");
  const transaction = (await cookies()).get(ONBOARDING_COOKIE)?.value;
  if (!transaction) redirect("/setup-complete?onboardingError=expired");
  let status: Status;
  try {
    status = await backendFetch<Status>("/api/oauth/onboarding/status", {
      method: "POST", body: JSON.stringify({ transaction }),
    });
  } catch {
    redirect("/setup-complete?onboardingError=expired");
  }
  redirect(onboardingDestination(status.status));
}
