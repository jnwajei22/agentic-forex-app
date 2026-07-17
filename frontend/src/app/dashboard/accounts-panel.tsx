"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppModal from "@/components/app-modal";
import ScheduleModal, { type ScheduleValue } from "@/components/schedule-modal";
import StatusBadge from "@/components/status-badge";
import { displayBroker, displayStrategy, displayValue } from "@/lib/display";

export type ConnectionSummary = { public_id: string; label?: string; broker_name?: string; server: string; environment: string; enabled: boolean; account_count: number; last_verified_at?: string; is_default: boolean };
export type ProfileSummary = { public_id: string; name: string; account_alias: string; execution_mode: string; strategy_name: string; strategy_version: string; enabled: boolean; autonomous_armed?: boolean; armed_until?: string; autonomous_shadow_mode?: boolean; decision_provider?: string; minimum_confidence?: number; risk?: { risk_per_trade_percent?: number; maximum_open_positions?: number } };
export type AccountSummary = { public_id: string; account_alias: string; account_name?: string; broker_name?: string; currency?: string; environment: string; is_demo?: number | null; available: boolean; locally_enabled: boolean; is_default_analysis: boolean; connection_id: string; profiles: ProfileSummary[] };
export type ScheduleSummary = { id: string; profile_ref: string; timezone: string; expression: { times: string[] }; enabled: boolean; next_run_at?: string; next_run_at_local?: string; last_run_at?: string; last_run_at_local?: string; last_run_status?: string; maximum_lateness_seconds: number; latest_dispatch?: { id: string; state: string; safe_retry: boolean; reason_code?: string; outcome?: string } };
export type WorkerHealth = { status: string; workers: Array<{ worker_id: string; status: string; last_heartbeat_at: string; healthy: boolean }> };
export type DailySummary = { date: string; outcomes: { TRADE: number; NO_TRADE: number; BLOCKED: number; ERROR: number }; daily_entry_count: number; kill_switch: boolean; armed_profiles: number };

type ConfirmDialog = { kind: "confirm"; title: string; description: string; action: () => Promise<void>; destructive?: boolean };
type RenameDialog = { kind: "rename"; account: AccountSummary; value: string };
type CreateDialog = { kind: "create"; account: AccountSummary; value: string };
type EditDialog = { kind: "edit"; account: AccountSummary; profile: ProfileSummary; mode: string };
type ArmDialog = { kind: "arm"; account: AccountSummary; profile: ProfileSummary; provider: string; shadow: boolean };
type DialogState = ConfirmDialog | RenameDialog | CreateDialog | EditDialog | ArmDialog | null;
type ScheduleDialog = { account: AccountSummary; profile: ProfileSummary; current?: ScheduleSummary } | null;

type AccountsPanelProps = {
  loadState: "loaded" | "unavailable";
  connections: ConnectionSummary[];
  accounts: AccountSummary[];
  profiles: ProfileSummary[];
  executions: Array<{ id: string; action_type: string; state: string; created_at: string }>;
  schedules: ScheduleSummary[];
  workerHealth: WorkerHealth;
  dailySummary: DailySummary;
};

export default function AccountsPanel({
  loadState, connections, accounts, executions, schedules, workerHealth, dailySummary,
}: AccountsPanelProps) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [profileStatus, setProfileStatus] = useState<Record<string, string>>({});
  const [dialog, setDialog] = useState<DialogState>(null);
  const [scheduleDialog, setScheduleDialog] = useState<ScheduleDialog>(null);

  async function mutate(path: string, method = "PUT", body?: object): Promise<boolean> {
    setBusy(path);
    setError("");
    try {
      const response = await fetch(`/api/backend/${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: unknown; message?: unknown };
        setError(typeof payload.message === "string" ? payload.message :
          typeof payload.detail === "string" ? payload.detail : "Unable to save this change. Try again.");
        return false;
      }
      router.refresh();
      return true;
    } catch {
      setError("Backend API unavailable. This change was not saved.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  function confirm(title: string, description: string, action: () => Promise<void>, destructive = true) {
    setDialog({ kind: "confirm", title, description, action, destructive });
  }

  async function checkStatus(profile: ProfileSummary) {
    setProfileStatus(current => ({ ...current, [profile.public_id]: "Checking…" }));
    const autonomous = profile.execution_mode === "demo_autonomous" || profile.autonomous_armed;
    try {
      const response = await fetch(`/api/backend/execution-profiles/${profile.public_id}/${autonomous ? "autonomy/status" : "demo-status"}`);
      const body = await response.json().catch(() => ({}));
      const reasons = Array.isArray(body.blocking_reasons)
        ? body.blocking_reasons.map((reason: unknown) => typeof reason === "object" && reason && "code" in reason ? String(reason.code) : String(reason))
        : [];
      setProfileStatus(current => ({
        ...current,
        [profile.public_id]: response.ok
          ? ((autonomous ? body.status === "ready" : body.ready_for_preview) ? "Ready" : `Blocked: ${reasons.map(displayValue).join(", ")}`)
          : "Status Unavailable",
      }));
    } catch {
      setProfileStatus(current => ({ ...current, [profile.public_id]: "Status Unavailable" }));
    }
  }

  if (loadState === "unavailable") {
    return <section className="management-section" aria-label="TradeLocker connections unavailable" />;
  }
  if (!connections.length) {
    return <section className="management-section empty-state">
      <div><div className="eyebrow">TradeLocker Connections</div><h2>No TradeLocker connections are configured.</h2>
        <p>The backend verified that no stored connections exist.</p></div>
      <a className="button" href="/connect-tradelocker?new=1">Add Connection</a>
    </section>;
  }

  const allProfiles = accounts.flatMap(account => account.profiles);
  return <>
    <section className="management-section">
      <div className="section-heading">
        <div><div className="eyebrow">TradeLocker Connections</div><h2>Connections, Accounts, and Execution Profiles</h2>
          <p>Manage stored accounts. The Selected Account is used only for general requests without an alias or profile.</p></div>
        <a className="button" href="/connect-tradelocker?new=1">Add Connection</a>
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="connection-list">{connections.map(connection => {
        const owned = accounts.filter(account => account.connection_id === connection.public_id);
        return <article className="card connection-card" key={connection.public_id}>
          <header className="connection-header">
            <div><h3>{connection.label || displayBroker(connection.broker_name || connection.server)}</h3>
              <p>{displayBroker(connection.broker_name || connection.server)}</p></div>
            <StatusBadge value={connection.enabled ? "connected" : "reauthentication_required"} />
          </header>
          <div className="metadata"><span>Last verified: {connection.last_verified_at ? new Date(connection.last_verified_at).toLocaleString() : "Not yet verified"}</span><span>Account count: {owned.length}</span></div>
          {!connection.enabled && <div className="notice">This connection could not refresh. Reauthenticate to restore account access.</div>}
          <div className="actions compact">
            <button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate(`broker/tradelocker/discover-accounts?connection_id=${encodeURIComponent(connection.public_id)}`, "POST")}>Refresh Accounts</button>
            <a className="button secondary" href={`/connect-tradelocker?connection_id=${encodeURIComponent(connection.public_id)}`}>Reauthenticate</a>
          </div>
          <details className="technical"><summary>Technical Details</summary><code>{connection.public_id}</code></details>
          <div className="account-stack">{owned.length ? owned.map(account => <article className="account-card" key={account.public_id}>
            <header className="account-header"><div><h4>{account.account_alias}</h4><p>{account.account_name || `${displayBroker(account.broker_name)} Account`}</p></div>
              <div className="badges"><StatusBadge value={account.is_demo === 1 ? "demo" : account.is_demo === 0 ? "live" : "unknown"} />
                <StatusBadge value={account.available && account.locally_enabled ? "active" : "unavailable"} />
                {account.is_default_analysis && <StatusBadge value="selected_account" />}</div></header>
            <div className="metadata"><span>Currency: {account.currency || "Unknown"}</span></div>
            {account.is_default_analysis && <p className="helper">Used for general account requests when no account alias or execution profile is specified. Execution-profile bindings remain unchanged.</p>}
            <details className="technical"><summary>Technical Details</summary><div>Account reference: <code>{account.public_id}</code></div></details>
            <div className="profile-list"><div className="label">Execution Profiles</div>
              {account.profiles.length ? account.profiles.map(profile => <div className="profile-row" key={profile.public_id}>
                <div className="profile-copy"><strong>{profile.name}</strong>
                  <small>{displayStrategy(profile.strategy_name, profile.strategy_version)} · {displayValue(profile.execution_mode)}</small>
                  <div className="badges inline-badges"><StatusBadge value={profile.enabled ? "enabled" : "disabled"} />{profile.autonomous_armed && <StatusBadge value="armed" />}</div>
                  <small>Risk per trade: {profile.risk?.risk_per_trade_percent ?? 0.25}% · Maximum open positions: {profile.risk?.maximum_open_positions ?? 1}</small>
                  {profile.autonomous_armed && <small>Armed until {profile.armed_until ? new Date(profile.armed_until).toLocaleString() : "expiry unavailable"} · {profile.autonomous_shadow_mode ? "Shadow Mode" : "Auto-submit"} · {displayValue(profile.decision_provider)}</small>}
                  {profileStatus[profile.public_id] && <small>{profileStatus[profile.public_id]}</small>}
                </div>
                <div className="actions compact profile-actions">
                  <button className="button secondary" onClick={() => void checkStatus(profile)}>Check Execution Status</button>
                  {account.is_demo === 1 && <button className="button secondary" onClick={() => setScheduleDialog({ account, profile, current: schedules.find(item => item.profile_ref === profile.public_id) })}>Schedule</button>}
                  {account.is_demo === 1 && (profile.autonomous_armed
                    ? <button className="button danger" onClick={() => confirm("Disarm Demo Autonomy", `Disarm ${profile.name}? Existing profile and schedule data will be preserved.`, async () => { await mutate(`execution-profiles/${profile.public_id}/autonomy/disarm`, "POST"); })}>Disarm Autonomy</button>
                    : <button className="button" onClick={() => setDialog({ kind: "arm", account, profile, provider: "openai", shadow: true })}>Arm Demo Autonomy</button>)}
                  <button className="button secondary" onClick={() => setDialog({ kind: "edit", account, profile, mode: profile.execution_mode })}>Edit Profile</button>
                  <button className={profile.enabled ? "button danger" : "button secondary"} onClick={() => confirm(`${profile.enabled ? "Disable" : "Enable"} Profile`, `${profile.enabled ? "Disable" : "Enable"} ${profile.name}?`, async () => { await mutate(`execution-profiles/${profile.public_id}`, "PUT", { enabled: !profile.enabled }); }, profile.enabled)}>{profile.enabled ? "Disable Profile" : "Enable Profile"}</button>
                  <button className="button danger" onClick={() => confirm("Delete Profile", `Permanently delete ${profile.name}? This action cannot be undone.`, async () => { await mutate(`execution-profiles/${profile.public_id}`, "DELETE"); })}>Delete Profile</button>
                </div>
              </div>) : <p>No execution profiles are attached to this account.</p>}
            </div>
            <div className="actions compact account-actions">
              <button className="button" onClick={() => setDialog({ kind: "create", account, value: `${account.account_alias} Hourly` })}>Create Profile</button>
              <button className="button secondary" onClick={() => setDialog({ kind: "rename", account, value: account.account_alias })}>Rename Alias</button>
              {!account.is_default_analysis && <button className="button gold" onClick={() => void mutate(`broker/accounts/${account.public_id}/default`)}>Make Selected Account</button>}
              <span className="destructive-spacer" />
              {account.locally_enabled && <button className="button danger" onClick={() => confirm("Disable Account", `Disable ${account.account_alias}? Profile history will be preserved.`, async () => { await mutate(`broker/accounts/${account.public_id}/disable`); })}>Disable Account</button>}
            </div>
          </article>) : <div className="notice">No accounts have been discovered for this connection. Refresh Accounts or reauthenticate.</div>}</div>
          <div className="destructive-zone">{connection.enabled && <button className="button danger" onClick={() => confirm("Disable Connection", `Disable ${connection.label || connection.server}? Stored accounts and profile history will be preserved.`, async () => { await mutate(`broker/connections/${connection.public_id}/disable`); })}>Disable Connection</button>}</div>
        </article>;
      })}</div>

      <article className="card operational-card">
        <div className="label">Autonomous Scheduler</div>
        <div className="badges inline-badges"><StatusBadge value={workerHealth.status} /><StatusBadge value={dailySummary.kill_switch ? "kill_switch_enabled" : "ready"} label={`Kill Switch ${dailySummary.kill_switch ? "Enabled" : "Disabled"}`} /></div>
        <p>Today UTC — Trade {dailySummary.outcomes.TRADE} · No Trade {dailySummary.outcomes.NO_TRADE} · Blocked {dailySummary.outcomes.BLOCKED} · Error {dailySummary.outcomes.ERROR} · Actual entries {dailySummary.daily_entry_count}</p>
        {schedules.length ? schedules.map(schedule => <div className="profile-row" key={schedule.id}><div><strong>{allProfiles.find(item => item.public_id === schedule.profile_ref)?.name || "Stored Profile"}</strong><small>{schedule.expression.times.join(", ")} {schedule.timezone}</small><small>Next local: {schedule.next_run_at_local ? new Date(schedule.next_run_at_local).toLocaleString() : "Paused"} · UTC: {schedule.next_run_at ? new Date(schedule.next_run_at).toISOString() : "Paused"}</small><small>Last: {schedule.last_run_status ? `${displayValue(schedule.last_run_status)} at ${schedule.last_run_at_local ? new Date(schedule.last_run_at_local).toLocaleString() : "unknown"}` : "No run yet"}</small></div>
          <div className="actions compact"><button className="button secondary" onClick={() => void mutate(`autonomous-schedules/${schedule.id}/${schedule.enabled ? "pause" : "resume"}`, "POST")}>{schedule.enabled ? "Pause" : "Resume"}</button>
            {schedule.latest_dispatch?.safe_retry && ["retry_exhausted", "error"].includes(schedule.latest_dispatch.state) && <button className="button secondary" onClick={() => confirm("Retry Safe Failure", "Retry this pre-submit failure with the same run key?", async () => { await mutate(`autonomous-schedule-runs/${schedule.latest_dispatch?.id}/retry`, "POST"); }, false)}>Retry Safe Failure</button>}
            <button className="button danger" onClick={() => confirm("Delete Schedule", "Delete this autonomous schedule? The profile will not be disarmed or deleted.", async () => { await mutate(`autonomous-schedules/${schedule.id}`, "DELETE"); })}>Delete</button></div></div>) : <p>No autonomous schedules are configured.</p>}
        <div className="actions compact"><button className="button danger" onClick={() => confirm("Enable Kill Switch", "Enable the global kill switch and block all new entries?", async () => { await mutate("operations/kill-switch/enable", "POST"); })}>Enable Kill Switch</button></div>
      </article>
      <article className="card operational-card"><div className="label">Recent Demo Executions</div>{executions.length ? executions.map(item => <p key={item.id}><strong>{displayValue(item.action_type)}</strong> · {displayValue(item.state)} · {new Date(item.created_at).toLocaleString()}</p>) : <p>No demo executions have been recorded.</p>}</article>
    </section>

    <ActionDialog dialog={dialog} busy={Boolean(busy)} setDialog={setDialog} mutate={mutate} />
    {scheduleDialog && <ScheduleModal key={scheduleDialog.profile.public_id} open profile={{
      name: scheduleDialog.profile.name,
      accountAlias: scheduleDialog.account.account_alias,
      strategy: displayStrategy(scheduleDialog.profile.strategy_name, scheduleDialog.profile.strategy_version),
      executionMode: displayValue(scheduleDialog.profile.execution_mode),
    }} initial={{ timezone: scheduleDialog.current?.timezone, times: scheduleDialog.current?.expression.times, enabled: scheduleDialog.current?.enabled }} saving={Boolean(busy)} onClose={() => setScheduleDialog(null)} onSave={async (value: ScheduleValue) => {
      const saved = await mutate(`execution-profiles/${scheduleDialog.profile.public_id}/autonomy/schedule`, "POST", { ...value, maximum_lateness_seconds: 600 });
      if (saved) setScheduleDialog(null);
    }} />}
  </>;
}

function ActionDialog({ dialog, busy, setDialog, mutate }: {
  dialog: DialogState;
  busy: boolean;
  setDialog: (dialog: DialogState) => void;
  mutate: (path: string, method?: string, body?: object) => Promise<boolean>;
}) {
  if (!dialog) return null;
  if (dialog.kind === "confirm") return <AppModal open title={dialog.title} description={dialog.description} onClose={() => setDialog(null)}><div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className={dialog.destructive ? "button danger-solid" : "button"} disabled={busy} onClick={async () => { await dialog.action(); setDialog(null); }}>{busy ? "Saving…" : "Confirm"}</button></div></AppModal>;

  const title = dialog.kind === "rename" ? "Rename Account Alias" : dialog.kind === "create" ? "Create Execution Profile" : dialog.kind === "edit" ? "Edit Execution Profile" : "Arm Demo Autonomy";
  return <AppModal open title={title} description={dialog.kind === "arm" ? "Arming applies only to the verified profile-bound demo account and expires automatically after 24 hours." : undefined} onClose={() => setDialog(null)}>
    <form onSubmit={async event => {
      event.preventDefault();
      let saved = false;
      if (dialog.kind === "rename") saved = Boolean(dialog.value.trim()) && await mutate(`broker/accounts/${dialog.account.public_id}/alias`, "PUT", { alias: dialog.value.trim() });
      if (dialog.kind === "create") saved = Boolean(dialog.value.trim()) && await mutate("execution-profiles", "POST", { name: dialog.value.trim(), account_id: dialog.account.public_id, execution_mode: "read_only" });
      if (dialog.kind === "edit") saved = await mutate(`execution-profiles/${dialog.profile.public_id}`, "PUT", { execution_mode: dialog.mode });
      if (dialog.kind === "arm") saved = await mutate(`execution-profiles/${dialog.profile.public_id}/autonomy/arm`, "POST", { arming_hours: 24, decision_provider: dialog.provider, minimum_confidence: 0.7, allowed_sessions: ["london", "new_york", "overlap"], shadow_mode: dialog.shadow });
      if (saved) setDialog(null);
    }}>
      {(dialog.kind === "rename" || dialog.kind === "create") && <div className="field"><label htmlFor="dialog-value">{dialog.kind === "rename" ? "Account alias" : "Profile name"}</label><input id="dialog-value" autoComplete="off" required maxLength={80} value={dialog.value} onChange={event => setDialog({ ...dialog, value: event.target.value })} /></div>}
      {dialog.kind === "create" && <div className="modal-summary"><p><strong>Account:</strong> {dialog.account.account_alias}</p><p><strong>Strategy:</strong> Hourly Forex v1</p><p><strong>Execution mode:</strong> Read Only</p></div>}
      {dialog.kind === "edit" && <div className="field"><label htmlFor="execution-mode">Execution mode</label><select id="execution-mode" value={dialog.mode} onChange={event => setDialog({ ...dialog, mode: event.target.value })}><option value="read_only">Read Only</option>{dialog.account.is_demo === 1 && <option value="demo_manual">Demo Manual</option>}</select></div>}
      {dialog.kind === "arm" && <><div className="field"><label htmlFor="decision-provider">Decision provider</label><select id="decision-provider" value={dialog.provider} onChange={event => setDialog({ ...dialog, provider: event.target.value })}><option value="openai">OpenAI</option><option value="no_trade">No Trade</option></select></div><label className="toggle-row"><input type="checkbox" checked={dialog.shadow} onChange={event => setDialog({ ...dialog, shadow: event.target.checked })} /><span>Shadow mode — decisions and previews only; no order submission</span></label>{!dialog.shadow && <div className="error">Auto-submit can place orders only after existing deterministic demo validation. The global kill switch remains authoritative.</div>}</>}
      <div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : dialog.kind === "arm" ? "Arm Demo Autonomy" : "Save"}</button></div>
    </form>
  </AppModal>;
}
