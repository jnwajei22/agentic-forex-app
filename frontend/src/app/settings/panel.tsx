"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppModal from "@/components/app-modal";
import StatusBadge from "@/components/status-badge";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";

export default function SettingsPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<TradeLockerStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [confirmDisable, setConfirmDisable] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/backend/broker/status");
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error();
      setStatus(parseTradeLockerStatus(body));
    } catch {
      setStatus(null);
      setError("Agentic Forex Desk could not reach the FastAPI backend. Stored connection status could not be verified.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    fetch("/api/backend/broker/status")
      .then(async response => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error();
        if (active) setStatus(parseTradeLockerStatus(body));
      })
      .catch(() => {
        if (active) setError("Agentic Forex Desk could not reach the FastAPI backend. Stored connection status could not be verified.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function disconnect() {
    setDeleting(true);
    setError("");
    try {
      const response = await fetch("/api/backend/broker/tradelocker", { method: "DELETE" });
      if (!response.ok) throw new Error();
      setConfirmDisable(false);
      router.refresh();
      await load();
    } catch {
      setError("Unable to disable the TradeLocker connection. No connection settings were changed.");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) return <div className="notice">Loading TradeLocker settings…</div>;
  return <>
    <section className="card settings-card">
      <div className="section-heading settings-heading"><div><div className="eyebrow">TradeLocker Connections</div><h2>Connection Management</h2><p>Credentials and connection-level controls are managed here, separately from account and execution-profile controls.</p></div>
        <StatusBadge value={error ? "unable_to_verify" : status?.status ?? "checking"} /></div>
      {error && <div className="degraded-banner compact" role="alert"><div><h3>Backend API Unavailable</h3><p>{error}</p></div><button className="button secondary" onClick={() => void load()}>Try Again</button></div>}
      {status?.status === "not_connected" && <div className="notice">TradeLocker setup required.</div>}
      {status?.selected_account && <div className="selected-summary"><StatusBadge value="selected_account" /><strong>{status.selected_account.account_alias ?? "Configured"}</strong><p>Used for general account requests when no account alias or execution profile is specified. Changing the Selected Account never changes a profile binding.</p><Link className="button secondary" href="/dashboard">Manage Execution Profiles</Link></div>}
      <div className="actions">
        <Link className="button" href="/connect-tradelocker">Update Credentials</Link>
        <Link className="button secondary" href="/connect-tradelocker?new=1">Add Connection</Link>
        {status && status.status !== "not_connected" && <Link className="button secondary" href="/connect-tradelocker">Reauthenticate</Link>}
        {status?.status === "connected_no_account" && <Link className="button gold" href="/select-account">Choose Selected Account</Link>}
        <button className="button secondary" type="button" onClick={() => void load()}>View Connection Status</button>
        {status && status.status !== "not_connected" && <button className="button danger" onClick={() => setConfirmDisable(true)}>Disable Connection</button>}
      </div>
    </section>
    <AppModal open={confirmDisable} title="Disable TradeLocker Connection" description="Accounts and profile history will be preserved, but broker access will be disabled until reauthenticated." onClose={() => setConfirmDisable(false)}>
      <div className="modal-actions"><button className="button secondary" onClick={() => setConfirmDisable(false)}>Cancel</button><button className="button danger-solid" disabled={deleting} onClick={() => void disconnect()}>{deleting ? "Disabling…" : "Disable Connection"}</button></div>
    </AppModal>
  </>;
}
