import Link from "next/link";

import { backendFetch } from "@/lib/backend";
import { requireSession } from "@/lib/session";

type BrokerStatus = {
  status: string;
  provider?: string;
  username?: string;
  server?: string;
  accountId?: string | null;
  accNum?: string | null;
};

export default async function DashboardPage() {
  const session = await requireSession();
  let broker: BrokerStatus = { status: "unavailable" };
  let error = "";
  try { broker = await backendFetch<BrokerStatus>("/api/broker/status"); }
  catch (caught) { error = caught instanceof Error ? caught.message : "Unable to load broker status."; }

  return (
    <main className="shell page">
      <div className="eyebrow">Dashboard</div>
      <h1 style={{ fontSize: 44 }}>Welcome back.</h1>
      {error && <div className="error">{error}</div>}
      <section className="grid">
        <article className="card"><div className="label">Signed in as</div><div className="value">{session.user.email ?? session.user.name}</div></article>
        <article className="card"><div className="label">Broker status</div><div className="value"><span className="status">{broker.status.replaceAll("_", " ")}</span></div></article>
        <article className="card"><div className="label">Selected account</div><div className="value">{broker.accountId ? `${broker.server ?? "TradeLocker"} · #${broker.accountId} · accNum ${broker.accNum}` : "Not selected"}</div></article>
      </section>
      <div className="actions">
        <Link className="button" href="/connect-tradelocker">{broker.status === "setup_required" ? "Connect TradeLocker" : "Update TradeLocker"}</Link>
        {broker.status === "account_selection_required" && <Link className="button secondary" href="/select-account">Select account</Link>}
        <Link className="button secondary" href="/settings">Settings</Link>
      </div>
    </main>
  );
}
