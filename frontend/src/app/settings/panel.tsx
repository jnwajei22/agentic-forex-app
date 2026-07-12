"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { backendErrorMessage } from "@/lib/backend-error-message";

type Status = { status: string; username?: string; server?: string; accountId?: string; accNum?: string };

export default function SettingsPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { fetch("/api/backend/broker/status").then(async response => { const body = await response.json(); if (!response.ok) throw { status: response.status, code: body.code }; setStatus(body); }).catch(caught => setError(typeof caught === "object" && caught !== null && "status" in caught ? backendErrorMessage(caught as { status: number; code?: string }) : "Backend API unavailable. Is the FastAPI server running?")).finally(() => setLoading(false)); }, []);

  async function disconnect() {
    if (!window.confirm("Remove your encrypted TradeLocker connection?")) return;
    setDeleting(true); setError("");
    const response = await fetch("/api/backend/broker/tradelocker", { method: "DELETE" }).catch(() => null);
    if (!response?.ok) { setError("Unable to disconnect TradeLocker."); setDeleting(false); return; }
    router.push("/dashboard"); router.refresh();
  }

  if (loading) return <div className="notice">Loading TradeLocker settings…</div>;
  return <section className="card" style={{ maxWidth: 680 }}>
    {error && <div className="error">{error}</div>}
    {status?.status === "setup_required" && <div className="notice">TradeLocker setup required.</div>}
    <div className="label">Connection status</div><div className="value">{status?.status?.replaceAll("_", " ") ?? "Unavailable"}</div>
    {status?.username && <p>{status.username} · {status.server}<br />{status.accountId ? `accountId ${status.accountId} · accNum ${status.accNum}` : "No account selected"}</p>}
    <div className="actions"><Link className="button" href="/connect-tradelocker">Update TradeLocker credentials</Link>{status?.status === "account_selection_required" && <Link className="button secondary" href="/select-account">Select TradeLocker account</Link>}{status && status.status !== "setup_required" && <button className="button danger" onClick={disconnect} disabled={deleting}>{deleting ? "Removing…" : "Disconnect TradeLocker"}</button>}</div>
  </section>;
}
