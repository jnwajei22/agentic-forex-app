import { authenticatedBackendClient } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";
import StatusBadge from "@/components/status-badge";
import RetryButton from "@/components/retry-button";
import { loadDashboardData, type DashboardData, type DashboardSection } from "@/lib/dashboard-data";
import AccountsPanel from "./accounts-panel";

type DashboardProps = { searchParams: Promise<{ connected?: string }> };

export default async function DashboardPage({ searchParams }: DashboardProps) {
  const session = await auth0.getSession();
  if (!session) return <main className="shell page"><div className="error">Please log in.</div></main>;

  const showConnectedBanner = (await searchParams).connected === "1";
  let tradeLocker: TradeLockerStatus | null = null;
  let connections:DashboardData["connections"]=[];let accounts:DashboardData["accounts"]=[];
  let profiles:DashboardData["profiles"]=[];let executions:DashboardData["executions"]=[];let schedules:DashboardData["schedules"]=[];
  let workerHealth:DashboardData["workerHealth"]={status:"unavailable",workers:[]};
  let dailySummary:DashboardData["dailySummary"]={date:"",outcomes:{TRADE:0,NO_TRADE:0,BLOCKED:0,MARKET_CLOSED:0,SKIPPED:0,ERROR:0},daily_entry_count:0,kill_switch:true,armed_profiles:0};
  let autonomousControls:DashboardData["autonomousControls"]={global_autonomous_kill_switch:true,demo_autonomous_enabled:false,live_autonomous_enabled:false,live_execution_supported:false,updated_at:"",effective:{demo:"blocked",live:"blocked"}};
  let sectionErrors:Partial<Record<DashboardSection,string>>={};
  let loadState: "loaded" | "unavailable" = "loaded";

  try {
    const data=await loadDashboardData(await authenticatedBackendClient());
    tradeLocker=data.status?parseTradeLockerStatus(data.status):null;
    ({connections,accounts,profiles,executions,schedules,workerHealth,dailySummary,autonomousControls}=data);
    sectionErrors=data.errors;loadState=data.coreUnavailable?"unavailable":"loaded";
  } catch {
    loadState = "unavailable";
  }

  const setupComplete = loadState === "loaded" && tradeLocker?.status === "ready";
  const selectedAccount = tradeLocker?.selected_account;
  const enabledProfiles = profiles.filter((profile) => profile.enabled).length;
  const systemState = loadState === "unavailable" ? "Unable to Verify" : autonomousControls.global_autonomous_kill_switch ? "Safety lock active" : autonomousControls.effective.demo === "active" ? "Demo automation active" : "Manual control";

  return <main className="dashboard-page">
    <div className="shell dashboard-shell">
      <header className="dashboard-hero">
        <div><div className="eyebrow">Operations desk</div><h1>Trading command center</h1><p>Monitor broker health, execution profiles, schedules, and autonomous safety controls from one workspace.</p></div>
        <div className="hero-account"><span className="avatar" aria-hidden="true">{String(session.user.email ?? session.user.name ?? "U").slice(0, 1).toUpperCase()}</span><div><small>Signed in as</small><strong>{session.user.email ?? session.user.name}</strong></div></div>
      </header>

      {showConnectedBanner && <div className="success dashboard-alert">TradeLocker connected successfully.</div>}
      {loadState === "unavailable" && <section className="degraded-banner" role="alert"><div><h2>Backend API Unavailable</h2><p>Stored connections and account state could not be verified. No trading controls were changed.</p></div><RetryButton label="Restore Backend Connection" /></section>}

      <section className="overview-strip" aria-label="Workspace overview">
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">01</div><div><span>Broker connection</span><strong>{loadState === "unavailable" ? "Unavailable" : setupComplete ? "TradeLocker ready" : "Setup required"}</strong></div><StatusBadge value={loadState === "unavailable" ? "unable_to_verify" : setupComplete ? "ready" : tradeLocker?.status ?? "checking"} /></article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">02</div><div><span>Selected TradeLocker Account</span><strong>{loadState === "unavailable" ? "Unable to Verify" : selectedAccount?.account_alias ?? "Not selected"}</strong></div>{selectedAccount && <StatusBadge value="selected_account" />}</article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">03</div><div><span>Execution profiles</span><strong>{enabledProfiles} enabled</strong></div><span className="overview-detail">{profiles.length} total</span></article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">04</div><div><span>System state</span><strong>{systemState}</strong></div><span className={`signal-dot ${loadState === "loaded" ? "is-online" : ""}`} aria-hidden="true" /></article>
      </section>

      {loadState === "loaded" && tradeLocker?.status === "not_connected" && <section className="setup-callout"><div><div className="eyebrow">Action required</div><h2>Connect your broker workspace</h2><p>Add a TradeLocker connection before creating execution profiles.</p></div><a className="button" href="/connect-tradelocker?new=1">Connect TradeLocker</a></section>}
      {loadState === "loaded" && tradeLocker?.status === "connected_no_account" && <section className="setup-callout"><div><div className="eyebrow">One step left</div><h2>Select a default account</h2><p>Choose which account should answer general requests without an explicit alias.</p></div><a className="button" href="/select-account">Select account</a></section>}
      {setupComplete && <section className="chatgpt-bar"><div><span className="signal-dot is-online" aria-hidden="true" /><div><strong>MCP workspace ready</strong><p>Continue in ChatGPT using this same authenticated account.</p></div></div><a className="button secondary" href="https://chatgpt.com" target="_blank" rel="noreferrer">Open ChatGPT</a></section>}

      <AccountsPanel loadState={loadState} sectionErrors={sectionErrors} connections={connections} accounts={accounts} profiles={profiles} executions={executions} schedules={schedules} workerHealth={workerHealth} dailySummary={dailySummary} autonomousControls={autonomousControls} />
    </div>
  </main>;
}
