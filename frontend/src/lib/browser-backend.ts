export class BrowserBackendError extends Error {
  status: number;
  payload: Record<string, unknown>;

  constructor(status: number, message: string, payload: Record<string, unknown> = {}) {
    super(message);
    this.name = "BrowserBackendError";
    this.status = status;
    this.payload = payload;
  }
}

function errorMessage(payload: Record<string, unknown>): string {
  const detail = payload.detail;
  const source = detail && typeof detail === "object" ? detail as Record<string, unknown> : payload;
  const message = source.message ?? source.error ?? (typeof detail === "string" ? detail : undefined);
  return typeof message === "string" && message.trim() ? message : "Unable to save this change. Try again.";
}

export async function browserBackendFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const normalized = path.replace(/^\/+/, "");
  const response = await fetch(`/api/backend/${normalized}`, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    if (process.env.NODE_ENV === "development") {
      console.error(`[browserBackendFetch] ${init.method ?? "GET"} ${normalized} failed with HTTP ${response.status}`);
    }
    throw new BrowserBackendError(response.status, errorMessage(payload), payload);
  }
  return payload as T;
}

export function browserBackendMutation<T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: object): Promise<T> {
  return browserBackendFetch<T>(path, {
    method,
    body: body ? JSON.stringify(body) : undefined,
  });
}

export type AutonomousControls = {
  global_autonomous_kill_switch: boolean;
  demo_autonomous_enabled: boolean;
  live_autonomous_enabled: boolean;
  live_execution_supported: boolean;
  updated_at: string;
  effective: { demo: string; live: string };
};

export type AutonomousControlPatch = Partial<Pick<AutonomousControls,
  "global_autonomous_kill_switch" | "demo_autonomous_enabled" | "live_autonomous_enabled"
>> & { live_confirmation?: string };

export async function updateAutonomousControls(
  previous: AutonomousControls,
  patch: AutonomousControlPatch,
  setControls: (controls: AutonomousControls) => void,
  request: typeof browserBackendMutation = browserBackendMutation,
): Promise<AutonomousControls> {
  try {
    const confirmed = await request<AutonomousControls>("autonomous-controls", "PATCH", patch);
    setControls(confirmed);
    return confirmed;
  } catch (error) {
    setControls(previous);
    throw error;
  }
}
