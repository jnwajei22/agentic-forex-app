import { backendFetch } from "@/lib/backend";
import { auth0 } from "@/lib/auth0";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";
import StatusBadge from "@/components/status-badge";
import RetryButton from "@/components/retry-button";
import AccountsPanel, {
  type AccountSummary,
  type ConnectionSummary,
  type DailySummary,
  type ProfileSummary,
  type ScheduleSummary,
  type WorkerHealth,
} from "./accounts-panel";

type DashboardProps = { searchParams: Promise<{ connected?: string }> };
type ExecutionSummary = { id: string; action_type: string; state: string; created_at: string };

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
  let dailySummary: DailySummary = {
    date: "", outcomes: { TRADE: 0, NO_TRADE: 0, BLOCKED: 0, ERROR: 0 },
    daily_entry_count: 0, kill_switch: true, armed_profiles: 0,
  };
  let loadState: "loaded" | "unavailable" = "loaded";

  try {
    const [statusResult, connectionsResult, accountsResult, profilesResult, executionsResult,
      schedulesResult, workerResult, dailyResult] = await Promise.all([
      backendFetch<unknown>("/api/broker/status"),
      backendFetch<{ connections: ConnectionSummary[] }>("/api/broker/connections"),
      backendFetch<{ accounts: AccountSummary[] }>("/api/broker/accounts"),
      backendFetch<{ profiles: ProfileSummary[] }>("/api/execution-profiles"),
      backendFetch<{ executions: ExecutionSummary[] }>("/api/demo-executions"),
      backendFetch<{ schedules: ScheduleSummary[] }>("/api/autonomous-schedules"),
      backendFetch<WorkerHealth>("/api/autonomous-worker-health"),
      backendFetch<DailySummary>("/api/autonomous-daily-summary"),
    ]);
    tradeLocker = parseTradeLockerStatus(statusResult);
    connections = connectionsResult.connections;
    accounts = accountsResult.accounts;
    profiles = profilesResult.profiles;
    executions = executionsResult.executions;
    schedules = schedulesResult.schedules;
    workerHealth = workerResult;
    dailySummary = dailyResult;
  } catch {
    loadState = "unavailable";
  }

  const setupComplete = loadState === "loaded" && tradeLocker?.status === "ready";
  const selectedAlias = tradeLocker?.selected_account?.account_alias ?? "Configured";
  const nextAction = loadState === "unavailable"
    ? "Restore Backend Connection"
    : tradeLocker?.status === "not_connected"
      ? "Configure a Connection"
      : tradeLocker?.status === "connected_no_account"
        ? "Select an Account"
        : setupComplete ? "Use in ChatGPT" : "Review Connection";

  return (
    <main className="shell page">
      <div className="eyebrow">Dashboard</div>
      <h1 className="page-title">Welcome back.</h1>
      {showConnectedBanner && <div className="success">TradeLocker connected successfully.</div>}
      {loadState === "unavailable" && <section className="degraded-banner" role="alert">
        <div>
          <h2>Backend API Unavailable</h2>
          <p>Agentic Forex Desk could not reach the FastAPI backend. Stored connections and account status could not be verified.</p>
        </div>
        <RetryButton />
      </section>}
      {loadState === "loaded" && tradeLocker?.status === "not_connected" &&
        <div className="notice">TradeLocker setup required.</div>}

      <section className="grid summary-grid">
        <article className="card"><div className="label">Signed In As</div><div className="value">{session.user.email ?? session.user.name}</div></article>
        <article className="card">
          <div className="label">TradeLocker Connection Status</div>
          <div className="value"><StatusBadge value={loadState === "unavailable" ? "unable_to_verify" : setupComplete ? "ready" : tradeLocker?.status ?? "checking"} /></div>
        </article>
        <article className="card">
          <div className="label">Selected TradeLocker Account</div>
          <div className="value">{loadState === "unavailable" ? "Unable to Verify" : tradeLocker?.selected_account ? selectedAlias : "Not Selected"}</div>
          {loadState === "loaded" && tradeLocker?.selected_account && <StatusBadge value="selected_account" />}
          <p>Used for general account requests when no account alias or execution profile is specified.</p>
        </article>
        <article className="card"><div className="label">Next Action</div><div className="value">{nextAction}</div></article>
      </section>

      {setupComplete && <section className="completion card">
        <div><h2>Continue in ChatGPT</h2><p>Open ChatGPT and use the Agentic Forex Desk MCP connector with this same login.</p></div>
        <a className="button" href="https://chatgpt.com" target="_blank" rel="noreferrer">Open ChatGPT</a>
      </section>}

      {loadState === "loaded" && tradeLocker?.status === "connected_no_account" &&
        <div className="actions"><a className="button" href="/select-account">Select TradeLocker Account</a></div>}

      <AccountsPanel
        loadState={loadState}
        connections={connections}
        accounts={accounts}
        profiles={profiles}
        executions={executions}
        schedules={schedules}
        workerHealth={workerHealth}
        dailySummary={dailySummary}
      />
    </main>
  );
}
