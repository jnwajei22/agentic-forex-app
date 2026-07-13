import { randomUUID } from "node:crypto";

import { auth0 } from "@/lib/auth0";
import {
  BackendError,
  backendFetchWithAuthorization,
  type BackendResponse,
} from "@/lib/backend";
import { signOnboardingAssertion } from "@/lib/onboarding-assertion";

export async function createOnboardingAssertion(transaction: string): Promise<string> {
  const session = await auth0.getSession();
  if (!session?.user.sub) {
    throw new BackendError(401, "An Auth0 session is required.", "not_authenticated");
  }
  const secret = process.env.ONBOARDING_ASSERTION_SECRET;
  const backend = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  const audienceBase = (process.env.ONBOARDING_ASSERTION_AUDIENCE ?? backend)?.replace(/\/$/, "");
  const issuer = (process.env.APP_BASE_URL ?? process.env.AUTH0_BASE_URL)?.replace(/\/$/, "");
  if (!secret || !backend || !audienceBase || !issuer) {
    throw new BackendError(503, "Onboarding assertion configuration is incomplete.", "backend_unavailable");
  }
  const now = Math.floor(Date.now() / 1000);
  return signOnboardingAssertion({
    subject: session.user.sub,
    transaction,
    secret,
    issuer,
    audience: `${audienceBase}/api/oauth/onboarding`,
    issuedAt: now,
    nonce: randomUUID(),
  });
}

export async function onboardingBackendFetchWithMetadata<T>(
  path: string,
  transaction: string,
  init?: RequestInit,
): Promise<BackendResponse<T>> {
  const assertion = await createOnboardingAssertion(transaction);
  return backendFetchWithAuthorization<T>(path, `Onboarding ${assertion}`, init);
}

export async function onboardingBackendFetch<T>(
  path: string,
  transaction: string,
  init?: RequestInit,
): Promise<T> {
  return (await onboardingBackendFetchWithMetadata<T>(path, transaction, init)).data;
}
