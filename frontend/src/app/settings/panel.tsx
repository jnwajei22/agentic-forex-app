"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { backendErrorMessage } from "@/lib/backend-error-message";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";

export default function SettingsPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<TradeLockerStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [executionMode, setExecutionMode] = useState("read_only");
  const [savingMode, setSavingMode] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch("/api/backend/broker/status").then(async response => {
        const body = await response.json();
        if (!response.ok) throw { status: response.status, code: body.code };
        setStatus(parseTradeLockerStatus(body));
      }),
      fetch("/api/backend/broker/tradelocker/execution-settings").then(async response => {
        if (response.ok) setExecutionMode((await response.json()).execution_mode);
      }),
    ]).catch(caught => setError(
      typeof caught === "object" && caught !== null && "status" in caught
        ? backendErrorMessage(caught as { status: number; code?: string })
        : "Backend API unavailable. Is the FastAPI server running?",
    )).finally(() => setLoading(false));
  }, []);

  async function disconnect() {
    if (!window.confirm("Remove your encrypted TradeLocker connection?")) return;
    setDeleting(true); setError("");
    const response = await fetch("/api/backend/broker/tradelocker", { method: "DELETE" }).catch(() => null);
    if (!response?.ok) { setError("Unable to disconnect TradeLocker."); setDeleting(false); return; }
    router.push("/dashboard"); router.refresh();
  }

  async function saveExecutionMode(mode: string) {
    if (mode !== "read_only" && !window.confirm("Enable broker-side execution on the selected TradeLocker demo account? Live accounts remain blocked.")) return;
    setSavingMode(true); setError("");
    const response = await fetch("/api/backend/broker/tradelocker/execution-settings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ execution_mode: mode }),
    }).catch(() => null);
    if (!response?.ok) {
      setError("Unable to update demo execution mode. Verify that the selected account is a demo account.");
      setSavingMode(false); return;
    }
    setExecutionMode((await response.json()).execution_mode); setSavingMode(false);
  }

  if (loading) return <div className="notice">Loading TradeLocker settings…</div>;
  return <section className="card" style={{ maxWidth: 680 }}>
    {error && <div className="error">{error}</div>}
    {status?.status === "not_connected" && <div className="notice">TradeLocker setup required.</div>}
    <div className="label">Connection status</div><div className="value">{status?.status?.replaceAll("_", " ") ?? "Unavailable"}</div>
    {status?.selected_account && <p>{status.selected_account.server}<br />accountId {status.selected_account.account_id} · accNum {status.selected_account.account_number}</p>}
    {status?.selected_account && <div className="notice">
      <label className="label" htmlFor="execution-mode">Demo execution mode</label>
      <select id="execution-mode" value={executionMode} disabled={savingMode || status.selected_account.environment !== "demo"} onChange={event => saveExecutionMode(event.target.value)}>
        <option value="read_only">Read only</option>
        <option value="demo_manual">Demo manual</option>
        <option value="demo_autonomous">Demo autonomous</option>
      </select>
      <p>Mode is account scoped. Broker writes also require the deployment administrator to disable the server kill switch.</p>
    </div>}
    <div className="actions"><Link className="button" href="/connect-tradelocker">Update TradeLocker credentials</Link>{status?.status === "connected_no_account" && <Link className="button secondary" href="/select-account">Select TradeLocker account</Link>}{status && status.status !== "not_connected" && <button className="button danger" onClick={disconnect} disabled={deleting}>{deleting ? "Removing…" : "Disconnect TradeLocker"}</button>}</div>
  </section>;
}
