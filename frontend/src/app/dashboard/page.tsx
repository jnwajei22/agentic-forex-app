import { backendFetch } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";
import StatusBadge from "@/components/status-badge";
import RetryButton from "@/components/retry-button";
import type { AutonomousControls } from "@/lib/browser-backend";
import type { AccountSummary, ConnectionSummary, DailySummary, ExecutionSummary, ProfileSummary, ScheduleSummary, WorkerHealth } from "@/lib/dashboard-contracts";
import AccountsPanel from "./accounts-panel";

type DashboardProps = { searchParams: Promise<{ connected?: string }> };

export default async function DashboardPage({ searchParams }: DashboardProps) {
  const session = await auth0.getSession();
  if (!session) return <main className="shell page"><div className="error">Please log in.</div></main>;

  const showConnectedBanner = (await searchParams).connected === "1";
  let tradeLocker: TradeLockerStatus | null = null;
  let connections: ConnectionSummary[] = [];
  let accounts: AccountSummary[] = [];
  let profiles: ProfileSummary[] = [];
  let executions: ExecutionSummary[] = [];
  let schedules: ScheduleSummary[] = [];
  let workerHealth: WorkerHealth = { status: "unavailable", workers: [] };
  let dailySummary: DailySummary = { date: "", outcomes: { TRADE: 0, NO_TRADE: 0, BLOCKED: 0, ERROR: 0 }, daily_entry_count: 0, kill_switch: true, armed_profiles: 0 };
  let autonomousControls: AutonomousControls = { global_autonomous_kill_switch: true, demo_autonomous_enabled: false, live_autonomous_enabled: false, live_execution_supported: false, updated_at: "", effective: { demo: "blocked", live: "blocked" } };
  let loadState: "loaded" | "unavailable" = "loaded";

  try {
    const [statusResult, connectionsResult, accountsResult, profilesResult, executionsResult, schedulesResult, workerResult, dailyResult, controlsResult] = await Promise.all([
      backendFetch<unknown>("/api/broker/status"),
      backendFetch<{ connections: ConnectionSummary[] }>("/api/broker/connections"),
      backendFetch<{ accounts: AccountSummary[] }>("/api/broker/accounts"),
      backendFetch<{ profiles: ProfileSummary[] }>("/api/execution-profiles"),
      backendFetch<{ executions: ExecutionSummary[] }>("/api/demo-executions"),
      backendFetch<{ schedules: ScheduleSummary[] }>("/api/autonomous-schedules"),
      backendFetch<WorkerHealth>("/api/autonomous-worker-health"),
      backendFetch<DailySummary>("/api/autonomous-daily-summary"),
      backendFetch<AutonomousControls>("/api/autonomous-controls"),
    ]);
    tradeLocker = parseTradeLockerStatus(statusResult);
    connections = connectionsResult.connections;
    accounts = accountsResult.accounts;
    profiles = profilesResult.profiles;
    executions = executionsResult.executions;
    schedules = schedulesResult.schedules;
    workerHealth = workerResult;
    dailySummary = dailyResult;
    autonomousControls = controlsResult;
  } catch {
    loadState = "unavailable";
  }

  const setupComplete = loadState === "loaded" && tradeLocker?.status === "ready";
  const selectedAccount = tradeLocker?.selected_account;
  const enabledProfiles = profiles.filter((profile) => profile.enabled).length;
  const systemState = loadState === "unavailable" ? "Unable to verify" : autonomousControls.global_autonomous_kill_switch ? "Safety lock active" : autonomousControls.effective.demo === "active" ? "Demo automation active" : "Manual control";

  return <main className="dashboard-page">
    <div className="shell dashboard-shell">
      <header className="dashboard-hero">
        <div><div className="eyebrow">Operations desk</div><h1>Trading command center</h1><p>Monitor broker health, execution profiles, schedules, and autonomous safety controls from one workspace.</p></div>
        <div className="hero-account"><span className="avatar" aria-hidden="true">{String(session.user.email ?? session.user.name ?? "U").slice(0, 1).toUpperCase()}</span><div><small>Signed in as</small><strong>{session.user.email ?? session.user.name}</strong></div></div>
      </header>

      {showConnectedBanner && <div className="success dashboard-alert">TradeLocker connected successfully.</div>}
      {loadState === "unavailable" && <section className="degraded-banner" role="alert"><div><h2>Backend API unavailable</h2><p>Stored connections and account state could not be verified. No trading controls were changed.</p></div><RetryButton /></section>}

      <section className="overview-strip" aria-label="Workspace overview">
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">01</div><div><span>Broker connection</span><strong>{loadState === "unavailable" ? "Unavailable" : setupComplete ? "TradeLocker ready" : "Setup required"}</strong></div><StatusBadge value={loadState === "unavailable" ? "unable_to_verify" : setupComplete ? "ready" : tradeLocker?.status ?? "checking"} /></article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">02</div><div><span>Selected account</span><strong>{loadState === "unavailable" ? "Unable to verify" : selectedAccount?.account_alias ?? "Not selected"}</strong></div>{selectedAccount && <StatusBadge value="selected_account" />}</article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">03</div><div><span>Execution profiles</span><strong>{enabledProfiles} enabled</strong></div><span className="overview-detail">{profiles.length} total</span></article>
        <article className="overview-card"><div className="overview-icon" aria-hidden="true">04</div><div><span>System state</span><strong>{systemState}</strong></div><span className={`signal-dot ${loadState === "loaded" ? "is-online" : ""}`} aria-hidden="true" /></article>
      </section>

      {loadState === "loaded" && tradeLocker?.status === "not_connected" && <section className="setup-callout"><div><div className="eyebrow">Action required</div><h2>Connect your broker workspace</h2><p>Add a TradeLocker connection before creating execution profiles.</p></div><a className="button" href="/connect-tradelocker?new=1">Connect TradeLocker</a></section>}
      {loadState === "loaded" && tradeLocker?.status === "connected_no_account" && <section className="setup-callout"><div><div className="eyebrow">One step left</div><h2>Select a default account</h2><p>Choose which account should answer general requests without an explicit alias.</p></div><a className="button" href="/select-account">Select account</a></section>}
      {setupComplete && <section className="chatgpt-bar"><div><span className="signal-dot is-online" aria-hidden="true" /><div><strong>MCP workspace ready</strong><p>Continue in ChatGPT using this same authenticated account.</p></div></div><a className="button secondary" href="https://chatgpt.com" target="_blank" rel="noreferrer">Open ChatGPT</a></section>}

      <AccountsPanel loadState={loadState} connections={connections} accounts={accounts} profiles={profiles} executions={executions} schedules={schedules} workerHealth={workerHealth} dailySummary={dailySummary} autonomousControls={autonomousControls} />
    </div>
  </main>;
}
