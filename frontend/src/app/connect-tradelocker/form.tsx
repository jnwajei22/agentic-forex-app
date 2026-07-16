"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { accountSelectionPath } from "@/lib/chatgpt-return";
import { afterCredentialsSaved } from "@/lib/onboarding-transaction";
import { getConnectionAlert, type ConnectionAlert } from "@/lib/connection-alert";

export default function ConnectTradeLockerForm({ returnTo, onboarding = false, initialAlert = null, connectionId = null, createNew = false }: { returnTo: string | null; onboarding?: boolean; initialAlert?: ConnectionAlert; connectionId?: string | null; createNew?: boolean }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [alert, setAlert] = useState<ConnectionAlert>(initialAlert);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setAlert(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const environment = String(form.get("environment"));
    const response = await fetch("/api/backend/broker/tradelocker/save-credentials", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: environment === "live" ? "https://live.tradelocker.com/backend-api" : "https://demo.tradelocker.com/backend-api",
        environment,
        connection_id: connectionId, create_new: createNew,
        username: form.get("username"), password: form.get("password"), server: form.get("server"),
      }),
    }).catch(() => null);
    if (!response?.ok) {
      const body = await response?.json().catch(() => ({}));
      const issue = body?.error === "tradelocker_credentials_rejected"
        ? "invalid_credentials"
        : response?.status && response.status >= 500
          ? "upstream_unavailable"
          : null;
      setAlert(getConnectionAlert({
        connectionIssue: issue,
        reconnectRequired: false,
        hasStoredConnection: false,
      }) ?? { kind: "error", message: body?.message ?? "Unable to save TradeLocker credentials." });
      const password = formElement.elements.namedItem("password");
      if (password instanceof HTMLInputElement) password.value = "";
      setLoading(false); return;
    }
    formElement.reset();
    router.push(afterCredentialsSaved(onboarding, accountSelectionPath(returnTo))); router.refresh();
  }

  return <form className="form" onSubmit={submit} autoComplete="off">
    {alert && <div className="error" role="alert">{alert.message}</div>}
    <div className="field"><label htmlFor="username">TradeLocker username or email</label><input id="username" name="username" type="email" required autoComplete="username" /></div>
    <div className="field"><label htmlFor="password">TradeLocker password</label><input id="password" name="password" type="password" required autoComplete="current-password" /></div>
    <div className="field"><label htmlFor="server">TradeLocker server</label><input id="server" name="server" required placeholder="Your TradeLocker server name" /><small>Use the TradeLocker server name provided by your broker or prop firm.</small></div>
    <div className="field"><label htmlFor="environment">Environment</label><select id="environment" name="environment" defaultValue="demo"><option value="demo">Demo</option><option value="live">Live</option></select></div>
    <button className="button" disabled={loading}>{loading ? "Saving securely…" : "Save and discover accounts"}</button>
  </form>;
}
