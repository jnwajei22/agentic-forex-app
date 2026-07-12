"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { accountSelectionPath } from "@/lib/chatgpt-return";
import { afterCredentialsSaved } from "@/lib/onboarding-transaction";

export default function ConnectTradeLockerForm({ returnTo, onboarding = false }: { returnTo: string | null; onboarding?: boolean }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const environment = String(form.get("environment"));
    const response = await fetch("/api/backend/broker/tradelocker/save-credentials", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: environment === "live" ? "https://live.tradelocker.com/backend-api" : "https://demo.tradelocker.com/backend-api",
        username: form.get("username"), password: form.get("password"), server: form.get("server"),
      }),
    }).catch(() => null);
    if (!response?.ok) {
      const body = await response?.json().catch(() => ({}));
      setError(body?.message ?? "Unable to save TradeLocker credentials."); setLoading(false); return;
    }
    formElement.reset();
    router.push(afterCredentialsSaved(onboarding, accountSelectionPath(returnTo))); router.refresh();
  }

  return <form className="form" onSubmit={submit} autoComplete="off">
    {error && <div className="error">{error}</div>}
    <div className="field"><label htmlFor="username">TradeLocker username or email</label><input id="username" name="username" type="email" required autoComplete="username" /></div>
    <div className="field"><label htmlFor="password">TradeLocker password</label><input id="password" name="password" type="password" required autoComplete="current-password" /></div>
    <div className="field"><label htmlFor="server">TradeLocker server</label><input id="server" name="server" required placeholder="Your TradeLocker server name" /><small>Use the TradeLocker server name provided by your broker or prop firm.</small></div>
    <div className="field"><label htmlFor="environment">Environment</label><select id="environment" name="environment" defaultValue="demo"><option value="demo">Demo</option><option value="live">Live</option></select></div>
    <button className="button" disabled={loading}>{loading ? "Saving securely…" : "Save and discover accounts"}</button>
  </form>;
}
