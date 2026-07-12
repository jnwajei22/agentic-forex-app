import { NextRequest, NextResponse } from "next/server";

import { BackendError, backendFetch } from "@/lib/backend";

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
]);

async function forward(request: NextRequest, segments: string[], method: string) {
  const path = segments.join("/");
  if (!allowed.has(path)) return NextResponse.json({ error: "Not found" }, { status: 404 });
  try {
    const body = method === "GET" || method === "DELETE" ? undefined : await request.text();
    const result = await backendFetch(`/api/${path}`, { method, body: body || undefined });
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
