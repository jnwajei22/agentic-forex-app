"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function ConnectTradeLockerForm() {
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
      setError(body?.error ?? "Unable to save TradeLocker credentials."); setLoading(false); return;
    }
    formElement.reset();
    router.push("/select-account"); router.refresh();
  }

  return <form className="form" onSubmit={submit} autoComplete="off">
    {error && <div className="error">{error}</div>}
    <div className="field"><label htmlFor="username">TradeLocker username or email</label><input id="username" name="username" type="email" required autoComplete="username" /></div>
    <div className="field"><label htmlFor="password">TradeLocker password</label><input id="password" name="password" type="password" required autoComplete="current-password" /></div>
    <div className="field"><label htmlFor="server">Broker server</label><input id="server" name="server" required placeholder="Your TradeLocker server name" /></div>
    <div className="field"><label htmlFor="environment">Environment</label><select id="environment" name="environment" defaultValue="demo"><option value="demo">Demo</option><option value="live">Live (read-only analysis)</option></select></div>
    <button className="button" disabled={loading}>{loading ? "Saving securely…" : "Save and discover accounts"}</button>
  </form>;
}
