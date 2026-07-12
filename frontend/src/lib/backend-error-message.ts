export type BackendFailure = { status: number; code?: string };

export function backendErrorMessage({ status, code }: BackendFailure): string {
  if (code === "not_authenticated") return "Please log in.";
  if (code === "token_acquisition_failed") return "Could not get backend access token. Log out and log in again.";
  if (status === 401 || status === 403) return "Backend rejected the access token. Check Auth0 audience/scopes.";
  if (code === "backend_unavailable" || status === 502 || status === 503 || status === 504) {
    return "Backend API unavailable. Is the FastAPI server running?";
  }
  return "Unable to load TradeLocker connection status.";
}
