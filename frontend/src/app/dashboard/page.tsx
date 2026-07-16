import Link from "next/link";

import { BackendError, backendFetch } from "@/lib/backend";
import { backendErrorMessage } from "@/lib/backend-error-message";
import { auth0 } from "@/lib/auth0";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";
import AccountsPanel, { type AccountSummary, type ConnectionSummary, type ProfileSummary } from "./accounts-panel";

type DashboardProps = { searchParams: Promise<{ connected?: string }> };

export default async function DashboardPage({ searchParams }: DashboardProps) {
  const session = await auth0.getSession();
  if (!session) return <main className="shell page"><div className="error">Please log in.</div></main>;
  const showConnectedBanner = (await searchParams).connected === "1";
  let tradeLocker: TradeLockerStatus = parseTradeLockerStatus(null);
  let error = "";
  let connections: ConnectionSummary[] = [], accounts: AccountSummary[] = [], profiles: ProfileSummary[] = [];
  try {
    tradeLocker = parseTradeLockerStatus(await backendFetch<unknown>("/api/broker/status"));
    connections = (await backendFetch<{ connections: ConnectionSummary[] }>("/api/broker/connections")).connections;
    accounts = (await backendFetch<{ accounts: AccountSummary[] }>("/api/broker/accounts")).accounts;
    profiles = (await backendFetch<{ profiles: ProfileSummary[] }>("/api/execution-profiles")).profiles;
  }
  catch (caught) { error = caught instanceof BackendError ? backendErrorMessage(caught) : "Unable to load TradeLocker connection status."; }

  const setupComplete = tradeLocker.status === "ready";
  const nextAction = tradeLocker.status === "not_connected"
    ? "Connect TradeLocker"
    : tradeLocker.status === "connected_no_account"
      ? "Select a TradeLocker account"
      : setupComplete ? "Use in ChatGPT" : "Review connection";

  return (
    <main className="shell page">
      <div className="eyebrow">Dashboard</div>
      <h1 style={{ fontSize: 44 }}>Welcome back.</h1>
      {showConnectedBanner && <div className="success">TradeLocker connected successfully.</div>}
      {error && <div className="error">{error}</div>}
      {tradeLocker.status === "not_connected" && <div className="notice">TradeLocker setup required.</div>}
      <section className="grid">
        <article className="card"><div className="label">Signed in as</div><div className="value">{session.user.email ?? session.user.name}</div></article>
        <article className="card"><div className="label">TradeLocker connection status</div><div className="value"><span className="status">{tradeLocker.status.replaceAll("_", " ")}</span></div></article>
        <article className="card"><div className="label">Selected TradeLocker account</div><div className="value">{tradeLocker.selected_account ? `${tradeLocker.selected_account.server} · #${tradeLocker.selected_account.account_id} · accNum ${tradeLocker.selected_account.account_number}` : "Not selected"}</div></article>
        <article className="card"><div className="label">Next action</div><div className="value">{nextAction}</div></article>
      </section>
      {setupComplete && <section className="completion card">
        <div>
          <h2>Continue in ChatGPT</h2>
          <p>Open ChatGPT and use the Agentic Forex App MCP connector. Use the same login account you used here.</p>
        </div>
        <a className="button" href="https://chatgpt.com" target="_blank" rel="noreferrer">Open ChatGPT</a>
      </section>}
      <div className="actions">
        <Link className="button" href="/connect-tradelocker">{tradeLocker.status === "not_connected" ? "Connect TradeLocker" : "Update TradeLocker credentials"}</Link>
        {tradeLocker.status === "connected_no_account" && <Link className="button secondary" href="/select-account">Select TradeLocker account</Link>}
        <Link className="button secondary" href="/settings">Settings</Link>
      </div>
      <AccountsPanel connections={connections} accounts={accounts} profiles={profiles} />
    </main>
  );
}
