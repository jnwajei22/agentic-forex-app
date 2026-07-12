import { auth0 } from "@/lib/auth0";

function safeError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : "Unknown error";
}

export class BackendError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: "not_authenticated" | "token_acquisition_failed" | "backend_error" | "backend_unavailable" = "backend_error",
    public payload?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "BackendError";
  }
}

export async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let session;
  try {
    session = await auth0.getSession();
  } catch (error) {
    console.error("[backendFetch] Failed to read the Auth0 session:", safeError(error));
    throw new BackendError(500, "Could not get backend access token.", "token_acquisition_failed");
  }
  if (!session) throw new BackendError(401, "Please log in.", "not_authenticated");

  let token: string;
  try {
    ({ token } = await auth0.getAccessToken());
  } catch (error) {
    console.error("[backendFetch] Auth0 access-token acquisition failed:", safeError(error));
    throw new BackendError(500, "Could not get backend access token.", "token_acquisition_failed");
  }
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!baseUrl) {
    console.error("[backendFetch] Backend API URL is not configured.");
    throw new BackendError(503, "Backend API URL is not configured.", "backend_unavailable");
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    console.error(`[backendFetch] Backend unavailable for ${path}:`, safeError(error));
    throw new BackendError(502, "Backend API unavailable.", "backend_unavailable");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const payload = typeof body.detail === "object" && body.detail ? body.detail : body;
    const message = payload.message ?? payload.error ?? (typeof body.detail === "string" ? body.detail : "Backend request failed.");
    console.error(`[backendFetch] Backend ${path} returned ${response.status}:`, message);
    throw new BackendError(response.status, String(message), "backend_error", payload);
  }
  return body as T;
}
