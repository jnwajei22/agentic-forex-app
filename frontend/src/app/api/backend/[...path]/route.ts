import { NextRequest, NextResponse } from "next/server";

import { BackendError, backendFetch } from "@/lib/backend";
import { onboardingBackendFetch } from "@/lib/onboarding-backend";

const allowed = new Set([
  "me",
  "broker/status",
  "broker/onboarding-status",
  "oauth/onboarding/bind",
  "oauth/onboarding/status",
  "oauth/onboarding/complete",
  "broker/tradelocker/save-credentials",
  "broker/tradelocker/discover-accounts",
  "broker/tradelocker/select-account",
  "broker/tradelocker",
  "broker/connections",
  "broker/accounts",
  "execution-profiles",
  "demo-executions",
  "autonomous-schedules",
  "autonomous-runs",
  "autonomous-daily-summary",
  "autonomous-worker-health",
  "autonomous-controls",
  "operations/kill-switch/enable",
]);

async function forward(request: NextRequest, segments: string[], method: string) {
  const path = segments.join("/");
  const dynamicAllowed = /^broker\/(accounts|connections)\/[^/]+\/(alias|default|disable)$/.test(path)
    || /^execution-profiles\/[^/]+$/.test(path);
  const profileStatusAllowed = /^execution-profiles\/[^/]+\/demo-status$/.test(path);
  const autonomousAllowed = /^execution-profiles\/[^/]+\/autonomy\/(status|arm|disarm|schedule)$/.test(path)
    || /^autonomous-schedules\/[^/]+(\/(pause|resume))?$/.test(path)
    || /^autonomous-schedule-runs\/[^/]+\/retry$/.test(path);
  const discoveryWithQuery = path === "broker/tradelocker/discover-accounts";
  if (!allowed.has(path) && !dynamicAllowed && !profileStatusAllowed && !autonomousAllowed && !discoveryWithQuery) return NextResponse.json({ error: "Not found" }, { status: 404 });
  try {
    const body = method === "GET" || method === "DELETE" ? undefined : await request.text();
    let result;
    if (path.startsWith("oauth/onboarding/")) {
      const parsed = body ? JSON.parse(body) as { transaction?: string } : {};
      if (!parsed.transaction) {
        return NextResponse.json({ error: "Missing onboarding transaction." }, { status: 401 });
      }
      result = await onboardingBackendFetch(`/api/${path}`, parsed.transaction, {
        method, body: body || undefined,
      });
    } else {
      result = await backendFetch(`/api/${path}${request.nextUrl.search}`, { method, body: body || undefined });
    }
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        error.payload ?? { error: error.message, code: error.code },
        { status: error.status },
      );
    }
    console.error(`[backend proxy] Unexpected error forwarding /api/${path}:`, error instanceof Error ? `${error.name}: ${error.message}` : "Unknown error");
    return NextResponse.json({ error: "Unable to reach the backend." }, { status: 502 });
  }
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path, "GET");
}

export async function POST(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path, "POST");
}

export async function DELETE(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path, "DELETE");
}

export async function PUT(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path, "PUT");
}

export async function PATCH(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path, "PATCH");
}
