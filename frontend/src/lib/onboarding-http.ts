export type OnboardingHttpDisposition = "session_expired" | "configuration_error" | "unavailable";

export function onboardingHttpDisposition(status: number): OnboardingHttpDisposition {
  if (status === 401 || status === 403 || status === 410) return "session_expired";
  if (status === 404) return "configuration_error";
  return "unavailable";
}
