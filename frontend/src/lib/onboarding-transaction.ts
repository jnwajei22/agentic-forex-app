export const ONBOARDING_COOKIE = "afd_oauth_transaction";
export const ONBOARDING_MAX_AGE_SECONDS = 10 * 60;

export function onboardingCookieOptions(production = process.env.NODE_ENV === "production") {
  return {
    httpOnly: true,
    secure: production,
    sameSite: "lax" as const,
    path: "/",
    maxAge: ONBOARDING_MAX_AGE_SECONDS,
  };
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
