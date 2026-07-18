import { auth0 } from "./auth0.ts";
import { classifyHttpStatus, classifyNetworkError, resolveBackendBaseUrl, safeBackendDiagnostic, type BackendFailureCategory } from "./backend-runtime.ts";

function safeError(error: unknown): string {
  return error instanceof Error ? error.name : "UnknownError";
}

export class BackendError extends Error {
  status:number;code:"not_authenticated"|"token_acquisition_failed"|"backend_error"|"backend_unavailable";
  payload?:Record<string,unknown>;endpoint?:string;contentType?:string;category:BackendFailureCategory;
  constructor(
    status: number,
    message: string,
    code: "not_authenticated" | "token_acquisition_failed" | "backend_error" | "backend_unavailable" = "backend_error",
    payload?: Record<string, unknown>,endpoint?: string,contentType?: string,category: BackendFailureCategory = "http_error",
  ) {
    super(message);
    this.name="BackendError";this.status=status;this.code=code;this.payload=payload;this.endpoint=endpoint;
    this.contentType=contentType;this.category=category;
  }
}

export type BackendResponse<T> = {
  data: T;
  status: number;
  contentType: string;
  endpoint: string;
  requestId?: string;
};

export async function backendFetchWithMetadata<T>(path: string, init?: RequestInit): Promise<BackendResponse<T>> {
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
  return backendFetchWithAuthorization<T>(path, `Bearer ${token}`, init);
}

export async function backendFetchWithAuthorization<T>(
  path: string,
  authorization: string,
  init?: RequestInit,
): Promise<BackendResponse<T>> {
  const method=init?.method ?? "GET";const diagnostic=safeBackendDiagnostic(path,method);
  let baseUrl: string;
  try { baseUrl=resolveBackendBaseUrl(); }
  catch {
    console.error("[backendFetch] configuration",diagnostic);
    throw new BackendError(503,"Backend API URL is not configured safely.","backend_unavailable",undefined,path,undefined,"configuration");
  }

  let response: Response;
  try {
    const timeout=AbortSignal.timeout(10_000);
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Authorization: authorization,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      signal:init?.signal ? AbortSignal.any([init.signal,timeout]) : timeout,
    });
  } catch (error) {
    const category=classifyNetworkError(error);
    console.error("[backendFetch] request failed",{...diagnostic,category});
    throw new BackendError(category==="timeout"?504:502,"Backend API unavailable.","backend_unavailable",undefined,path,undefined,category);
  }
  const contentType = response.headers.get("content-type") ?? "";
  const text = await response.text();
  let body: Record<string, unknown> = {};
  if (text && contentType.toLowerCase().includes("json")) {
    try { body = JSON.parse(text) as Record<string, unknown>; }
    catch { body = {}; }
  }
  if (!response.ok) {
    const payload = typeof body.detail === "object" && body.detail ? body.detail as Record<string, unknown> : body;
    const message = payload.message ?? payload.error ?? (typeof body.detail === "string" ? body.detail : "Backend request failed.");
    const category=classifyHttpStatus(response.status);
    console.error("[backendFetch] HTTP failure",{...diagnostic,status:response.status,category});
    throw new BackendError(response.status, String(message), "backend_error", payload, path, contentType,category);
  }
  if (!contentType.toLowerCase().includes("json")) {
    console.error("[backendFetch] invalid response",{...diagnostic,status:response.status,category:"http_error"});
    throw new BackendError(502, "Backend returned a non-JSON response.", "backend_error", {}, path, contentType);
  }
  if (process.env.BACKEND_DIAGNOSTICS_ENABLED === "true") {
    console.info("[backendFetch] response", {...diagnostic, status: response.status});
  }
  return {
    data: body as T,
    status: response.status,
    contentType,
    endpoint: `${baseUrl}${path}`,
    requestId: typeof body.request_id === "string" ? body.request_id : undefined,
  };
}

export async function authenticatedBackendClient():Promise<<T>(path:string,init?:RequestInit)=>Promise<T>> {
  let token:string;
  try { ({token}=await auth0.getAccessToken()); }
  catch {
    console.error("[backendFetch] access token unavailable",{runtime:"server",audienceConfigured:Boolean(process.env.AUTH0_AUDIENCE)});
    throw new BackendError(401,"Could not get backend access token.","token_acquisition_failed",undefined,undefined,undefined,"authentication");
  }
  const authorization=`Bearer ${token}`;
  return async <T>(path:string,init?:RequestInit)=>(await backendFetchWithAuthorization<T>(path,authorization,init)).data;
}

export async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return (await backendFetchWithMetadata<T>(path, init)).data;
}
