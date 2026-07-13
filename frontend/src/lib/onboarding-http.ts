export type OnboardingHttpDisposition = "session_expired" | "configuration_error" | "unavailable";

export function onboardingHttpDisposition(status: number): OnboardingHttpDisposition {
  if (status === 401 || status === 403 || status === 410) return "session_expired";
  if (status === 404) return "configuration_error";
  return "unavailable";
}

export type OnboardingBindDisposition = "owner" | "expired" | "configuration" | "unavailable";

export function onboardingBindDisposition(status: number, code?: string): OnboardingBindDisposition {
  if (status === 403 && (code === "onboarding_owner_mismatch" || code === "onboarding_transaction_mismatch")) {
    return "owner";
  }
  if (status === 401 || status === 410) return "expired";
  if (status === 404) return "configuration";
  return "unavailable";
}
