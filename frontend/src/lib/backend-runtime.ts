export type BackendFailureCategory =
  | "configuration"
  | "authentication"
  | "unauthorized"
  | "not_found"
  | "timeout"
  | "dns"
  | "tls"
  | "server_error"
  | "http_error"
  | "network";

type RuntimeEnvironment = Record<string, string | undefined>;

function hostname(value?: string): string | null {
  if (!value) return null;
  try { return new URL(value.startsWith("http") ? value : `https://${value}`).hostname; }
  catch { return null; }
}

export function resolveBackendBaseUrl(env: RuntimeEnvironment = process.env): string {
  const configured = env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");
  if (!configured) throw new Error("backend_url_not_configured");
  let target: URL;
  try { target = new URL(configured); }
  catch { throw new Error("backend_url_invalid"); }
  if (!/^https?:$/.test(target.protocol)) throw new Error("backend_url_invalid_protocol");
  if (env.NODE_ENV === "production") {
    if (["localhost", "127.0.0.1", "::1"].includes(target.hostname)) throw new Error("backend_url_localhost_in_production");
    const frontendHosts = [hostname(env.APP_BASE_URL), hostname(env.AUTH0_BASE_URL), hostname(env.VERCEL_URL)].filter(Boolean);
    if (frontendHosts.includes(target.hostname)) throw new Error("backend_url_points_to_frontend");
    if (target.protocol !== "https:") throw new Error("backend_url_requires_https");
  }
  return target.origin + target.pathname.replace(/\/$/, "");
}

export function safeBackendDiagnostic(path: string, method: string, env: RuntimeEnvironment = process.env) {
  let backendHostname: string | null = null;
  try { backendHostname = new URL(resolveBackendBaseUrl(env)).hostname; } catch { /* reported by configured=false */ }
  return {
    apiBaseUrlConfigured: Boolean(env.NEXT_PUBLIC_API_BASE_URL),
    auth0AudienceConfigured: Boolean(env.AUTH0_AUDIENCE),
    auth0IssuerConfigured: Boolean(env.AUTH0_ISSUER_BASE_URL || env.AUTH0_DOMAIN),
    backendHostname,
    runtime: typeof window === "undefined" ? "server" : "client",
    path: path.startsWith("/") ? path : `/${path}`,
    method: method.toUpperCase(),
  };
}

export function classifyNetworkError(error: unknown): BackendFailureCategory {
  const value = error as { name?: string; code?: string; cause?: { code?: string } };
  const code = value?.cause?.code ?? value?.code ?? "";
  if (value?.name === "AbortError" || value?.name === "TimeoutError") return "timeout";
  if (["ENOTFOUND", "EAI_AGAIN"].includes(code)) return "dns";
  if (code.startsWith("CERT_") || code.includes("TLS")) return "tls";
  return "network";
}

export function classifyHttpStatus(status: number): BackendFailureCategory {
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 404) return "not_found";
  if (status >= 500) return "server_error";
  return "http_error";
}
