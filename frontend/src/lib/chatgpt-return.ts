const ALLOWED_CHATGPT_ORIGINS = new Set([
  "https://chatgpt.com",
  "https://chat.openai.com",
]);

export function safeChatGptReturnTo(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ALLOWED_CHATGPT_ORIGINS.has(url.origin) ? value : null;
  } catch {
    return null;
  }
}

export function withReturnTo(path: string, returnTo: string | null): string {
  return returnTo ? `${path}?returnTo=${encodeURIComponent(returnTo)}` : path;
}

export function accountSelectionPath(returnTo: string | null): string {
  return withReturnTo("/select-account", returnTo);
}

export function completedSetupPath(returnTo: string | null): string {
  return returnTo
    ? withReturnTo("/setup-complete", returnTo)
    : "/dashboard?connected=1";
}
