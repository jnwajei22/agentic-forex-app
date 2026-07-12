import Link from "next/link";

import { auth0 } from "@/lib/auth0";

export default async function Home() {
  const session = await auth0.getSession();
  return (
    <main className="shell hero">
      <div className="eyebrow">TradeLocker setup portal</div>
      <h1>Connect TradeLocker to ChatGPT MCP.</h1>
      <p>Connect your TradeLocker account once, then use the MCP server from ChatGPT.</p>
      <div className="actions">
        <Link className="button" href={session ? "/dashboard" : "/auth/login?returnTo=/dashboard"}>
          {session ? "Open dashboard" : "Log in"}
        </Link>
        <a className="button secondary" href="#connection">How it works</a>
      </div>
      <section id="connection" className="grid">
        <article className="card"><h2>One-time setup</h2><p>Save your TradeLocker credentials and select the TradeLocker account for the MCP server.</p></article>
        <article className="card"><h2>Use it from ChatGPT</h2><p>After setup, ask ChatGPT to use the Agentic Forex Desk MCP server.</p></article>
      </section>
    </main>
  );
}
