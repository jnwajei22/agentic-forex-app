"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Account = { accountId?: string | number; accNum?: string | number; name?: string; currency?: string; status?: string };

export default function AccountSelector() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/backend/broker/tradelocker/discover-accounts", { method: "POST" })
      .then(async response => {
        const body = await response.json();
        if (!response.ok || body.status === "error" || body.status === "setup_required") throw new Error(body.error ?? body.message ?? "Connect TradeLocker first.");
        if (active) setAccounts(body.accounts ?? []);
      })
      .catch(caught => active && setError(caught instanceof Error ? caught.message : "Unable to discover accounts."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  async function save() {
    const account = accounts[Number(selected)];
    if (!account || account.accountId == null || account.accNum == null) { setError("Select a valid account."); return; }
    setSaving(true); setError("");
    const response = await fetch("/api/backend/broker/tradelocker/select-account", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accountId: String(account.accountId), accNum: String(account.accNum) }),
    }).catch(() => null);
    if (!response?.ok) { const body = await response?.json().catch(() => ({})); setError(body?.error ?? "Unable to select the account."); setSaving(false); return; }
    router.push("/dashboard"); router.refresh();
  }

  if (loading) return <div className="notice">Discovering TradeLocker accounts…</div>;
  return <section style={{ maxWidth: 680 }}>
    {error && <div className="error">{error}</div>}
    {!error && accounts.length === 0 && <div className="notice">No accounts were returned. Verify the username, password, and server.</div>}
    <div className="account-list">{accounts.map((account, index) => <label className="account" key={`${account.accountId}-${account.accNum}`}><input type="radio" name="account" value={index} checked={selected === String(index)} onChange={event => setSelected(event.target.value)} /><span><strong>{account.name ?? `Account #${account.accountId}`}</strong><br /><span className="label">accountId {account.accountId} · accNum {account.accNum}{account.currency ? ` · ${account.currency}` : ""}</span></span></label>)}</div>
    <button className="button" onClick={save} disabled={!selected || saving}>{saving ? "Saving selection…" : "Use selected account"}</button>
  </section>;
}
