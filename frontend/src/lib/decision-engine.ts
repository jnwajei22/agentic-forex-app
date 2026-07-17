export type ProviderReadiness = {
  status: string;
  label: string;
  ready: boolean;
  blocking_reasons: string[];
  api_key_configured: boolean;
  provider_available: boolean;
};

export function validateMinimumConfidence(value: string | number): string | null {
  const confidence = typeof value === "number" ? value : Number(value);
  if (String(value).trim() === "" || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    return "Minimum Confidence must be a number between 0 and 1.";
  }
  return null;
}

export function displayedProviderReadiness(
  provider: "openai" | "no_trade",
  modelIdentifier: string,
  backend: ProviderReadiness | undefined,
): { status: string; label: string } {
  if (provider === "no_trade") return { status: "testing_only", label: "Testing Only" };
  if (backend && !backend.provider_available) return { status: "provider_unavailable", label: "Provider Unavailable" };
  if (backend && !backend.api_key_configured) return { status: "api_key_missing", label: "API Key Missing" };
  if (!modelIdentifier.trim()) return { status: "model_not_selected", label: "Model Not Selected" };
  return { status: "ready", label: "Ready" };
}
