import Link from "next/link";

import { BackendError, backendFetch } from "@/lib/backend";
import { backendErrorMessage } from "@/lib/backend-error-message";
import { auth0 } from "@/lib/auth0";

type TradeLockerStatus = {
  status: string;
  provider?: string;
  username?: string;
  server?: string;
  accountId?: string | null;
  accNum?: string | null;
};

type DashboardProps = { searchParams: Promise<{ connected?: string }> };

export default async function DashboardPage({ searchParams }: DashboardProps) {
  const session = await auth0.getSession();
  if (!session) return <main className="shell page"><div className="error">Please log in.</div></main>;
  const showConnectedBanner = (await searchParams).connected === "1";
  let tradeLocker: TradeLockerStatus = { status: "unavailable" };
  let error = "";
  try { tradeLocker = await backendFetch<TradeLockerStatus>("/api/broker/status"); }
  catch (caught) { error = caught instanceof BackendError ? backendErrorMessage(caught) : "Unable to load TradeLocker connection status."; }

  const setupComplete = tradeLocker.status === "connected" && Boolean(tradeLocker.accountId);
  const nextAction = tradeLocker.status === "setup_required"
    ? "Connect TradeLocker"
    : tradeLocker.status === "account_selection_required"
      ? "Select a TradeLocker account"
      : setupComplete ? "Use in ChatGPT" : "Review connection";

  return (
    <main className="shell page">
      <div className="eyebrow">Dashboard</div>
      <h1 style={{ fontSize: 44 }}>Welcome back.</h1>
      {showConnectedBanner && <div className="success">TradeLocker connected successfully.</div>}
      {error && <div className="error">{error}</div>}
      {tradeLocker.status === "setup_required" && <div className="notice">TradeLocker setup required.</div>}
      <section className="grid">
        <article className="card"><div className="label">Signed in as</div><div className="value">{session.user.email ?? session.user.name}</div></article>
        <article className="card"><div className="label">TradeLocker connection status</div><div className="value"><span className="status">{tradeLocker.status.replaceAll("_", " ")}</span></div></article>
        <article className="card"><div className="label">Selected TradeLocker account</div><div className="value">{tradeLocker.accountId ? `${tradeLocker.server ?? "TradeLocker"} · #${tradeLocker.accountId} · accNum ${tradeLocker.accNum}` : "Not selected"}</div></article>
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
        <Link className="button" href="/connect-tradelocker">{tradeLocker.status === "setup_required" ? "Connect TradeLocker" : "Update TradeLocker credentials"}</Link>
        {tradeLocker.status === "account_selection_required" && <Link className="button secondary" href="/select-account">Select TradeLocker account</Link>}
        <Link className="button secondary" href="/settings">Settings</Link>
      </div>
    </main>
  );
}
