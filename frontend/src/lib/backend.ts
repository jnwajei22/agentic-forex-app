import { auth0 } from "@/lib/auth0";

export class BackendError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await auth0.getSession();
  if (!session?.accessToken) throw new BackendError(401, "Please log in again.");
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!baseUrl) throw new BackendError(500, "Backend API URL is not configured.");

  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${session.accessToken}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new BackendError(response.status, body.detail ?? body.message ?? "Backend request failed.");
  }
  return body as T;
}
