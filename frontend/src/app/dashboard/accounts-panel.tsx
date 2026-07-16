"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export type ConnectionSummary = { public_id: string; label?: string; server: string; environment: string; enabled: boolean; account_count: number };
export type AccountSummary = { public_id: string; account_alias: string; account_name?: string; environment: string; available: boolean; locally_enabled: boolean; is_default_analysis: boolean; connection_id: string; connection_label?: string };
export type ProfileSummary = { public_id: string; name: string; account_alias: string; execution_mode: string; strategy_name: string; strategy_version: string };

export default function AccountsPanel({ connections, accounts, profiles }: { connections: ConnectionSummary[]; accounts: AccountSummary[]; profiles: ProfileSummary[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  async function mutate(path: string, method = "PUT", body?: object) {
    setBusy(path); setError("");
    const response = await fetch(`/api/backend/${path}`, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
    if (!response.ok) setError(String((await response.json().catch(() => ({}))).detail ?? "Unable to update account."));
    else router.refresh();
    setBusy(null);
  }
  function rename(account: AccountSummary) {
    const alias = window.prompt("New account alias", account.account_alias)?.trim();
    if (alias && alias !== account.account_alias) void mutate(`broker/accounts/${account.public_id}/alias`, "PUT", { alias });
  }
  function createProfile(account: AccountSummary) {
    const name = window.prompt(`Profile name for ${account.account_alias}`, `${account.account_alias}-hourly`)?.trim();
    if (name) void mutate("execution-profiles", "POST", { name, account_id: account.public_id });
  }
  return <section style={{ marginTop: 28 }}>
    <div className="actions" style={{ justifyContent: "space-between" }}><div><div className="eyebrow">Accounts</div><h2>TradeLocker accounts</h2></div><a className="button secondary" href="/connect-tradelocker?new=1">Add connection</a></div>
    {error && <div className="error">{error}</div>}
    {connections.map(connection => <article className="card" key={connection.public_id} style={{ marginBottom: 16 }}>
      <div className="label">{connection.label ?? connection.server} · {connection.environment} · {connection.enabled ? "active" : "disabled"}</div>
      <div className="actions">
        <button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate(`broker/tradelocker/discover-accounts?connection_id=${encodeURIComponent(connection.public_id)}`, "POST")}>Refresh accounts</button>
        <a className="button secondary" href={`/connect-tradelocker?connection_id=${encodeURIComponent(connection.public_id)}`}>Reauthenticate</a>
        {connection.enabled && <button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate(`broker/connections/${connection.public_id}/disable`)}>Disable</button>}
      </div>
      {accounts.filter(account => account.connection_id === connection.public_id).map(account => <div key={account.public_id} style={{ borderTop: "1px solid var(--border)", marginTop: 14, paddingTop: 14 }}>
        <div className="value">{account.account_alias} {account.is_default_analysis && <span className="status">default</span>}</div>
        <p>{account.account_name ?? "TradeLocker account"} · {account.environment} · {account.available ? "available" : "unavailable"}</p>
        <div className="actions"><button className="button secondary" onClick={() => rename(account)}>Rename alias</button>{!account.is_default_analysis && <button className="button secondary" onClick={() => void mutate(`broker/accounts/${account.public_id}/default`)}>Make default</button>}{account.locally_enabled && <button className="button secondary" onClick={() => void mutate(`broker/accounts/${account.public_id}/disable`)}>Disable</button>}<button className="button secondary" onClick={() => createProfile(account)}>Create profile</button></div>
      </div>)}
    </article>)}
    <article className="card"><div className="label">Execution profiles</div>{profiles.length ? profiles.map(profile => <div key={profile.public_id} style={{ marginTop: 12 }}><p><strong>{profile.name}</strong> · {profile.account_alias} · {profile.strategy_name} v{profile.strategy_version} · {profile.execution_mode}</p><div className="actions"><button className="button secondary" onClick={() => void mutate(`execution-profiles/${profile.public_id}`, "PUT", { execution_mode: profile.execution_mode === "disabled" ? "read_only" : "disabled" })}>{profile.execution_mode === "disabled" ? "Enable read-only" : "Disable"}</button><button className="button secondary" onClick={() => void mutate(`execution-profiles/${profile.public_id}`, "DELETE")}>Delete</button></div></div>) : <p>No profiles configured. New profiles start read-only.</p>}</article>
  </section>;
}
