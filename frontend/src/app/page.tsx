import Link from "next/link";

import { auth0 } from "@/lib/auth0";

export default async function Home() {
  const session = await auth0.getSession();
  return (
    <main className="shell hero">
      <div className="eyebrow">Read-only market intelligence</div>
      <h1>TradeLocker charts with clearer forex context.</h1>
      <p>
        Connect your own TradeLocker account to analyze candles, indicators, spreads,
        and multi-timeframe confluence. Agentic Forex Desk does not submit trades.
      </p>
      <div className="actions">
        <Link className="button" href={session ? "/dashboard" : "/login"}>
          {session ? "Open dashboard" : "Log in to begin"}
        </Link>
        <a className="button secondary" href="#safety">How it works</a>
      </div>
      <section id="safety" className="grid">
        <article className="card"><h2>Private connection</h2><p>Your broker password is sent directly to the backend and encrypted at rest.</p></article>
        <article className="card"><h2>Analysis only</h2><p>No order submission, position closing, cancellation, or modification tools.</p></article>
      </section>
    </main>
  );
}
