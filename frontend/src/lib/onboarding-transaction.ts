export const ONBOARDING_COOKIE = "afd_oauth_transaction";
export const ONBOARDING_MAX_AGE_SECONDS = 10 * 60;

export function onboardingCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: ONBOARDING_MAX_AGE_SECONDS,
  };
}

export function onboardingDestination(status: string): string {
  if (status === "setup_required") return "/connect-tradelocker";
  if (status === "account_selection_required") return "/select-account";
  if (status === "connected") return "/setup-complete";
  throw new Error("Unknown TradeLocker connection status.");
}

export function isAllowedOAuthCallback(value: string): boolean {
  try {
    const origin = new URL(value).origin;
    return origin === "https://chatgpt.com" || origin === "https://chat.openai.com";
  } catch {
    return false;
  }
}

export function afterCredentialsSaved(onboarding: boolean, fallback: string): string {
  return onboarding ? "/onboarding" : fallback;
}

export function afterAccountSelected(onboarding: boolean, fallback: string): string {
  return onboarding ? "/onboarding" : fallback;
}
