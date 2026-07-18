"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppModal from "@/components/app-modal";
import StatusBadge from "@/components/status-badge";
import { displayBroker, displayStrategy, displayValue } from "@/lib/display";
import {
  BrowserBackendError,
  browserBackendFetch,
  browserBackendMutation,
  updateAutonomousControls,
  type AutonomousControls,
  type AutonomousControlPatch,
} from "@/lib/browser-backend";
import type {
  AccountSummary,
  ConnectionSummary,
  DailySummary,
  ExecutionSummary,
  ProfileSummary,
  ScheduleSummary,
  WorkerHealth,
} from "@/lib/dashboard-contracts";
import type { DashboardSection } from "@/lib/dashboard-data";

export type { AccountSummary, ConnectionSummary, DailySummary, ProfileSummary, ScheduleSummary, WorkerHealth } from "@/lib/dashboard-contracts";

type Props = {
  loadState: "loaded" | "unavailable";
  sectionErrors:Partial<Record<DashboardSection,string>>;
  connections: ConnectionSummary[];
  accounts: AccountSummary[];
  profiles: ProfileSummary[];
  executions: ExecutionSummary[];
  schedules: ScheduleSummary[];
  workerHealth: WorkerHealth;
  dailySummary: DailySummary;
  autonomousControls: AutonomousControls;
};

type Dialog =
  | { kind: "rename"; account: AccountSummary; value: string }
  | { kind: "create"; account: AccountSummary; value: string }
  | { kind: "edit"; account: AccountSummary; profile: ProfileSummary; name: string; enabled: boolean; allowedPairs: string }
  | { kind: "delete"; profile: ProfileSummary }
  | { kind: "live"; confirmation: string }
  | null;

function formatDate(value?: string) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function AccountsPanel({ loadState, sectionErrors, connections, accounts, executions, schedules, workerHealth, dailySummary, autonomousControls }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [controls, setControls] = useState(autonomousControls);
  const [profileStatus, setProfileStatus] = useState<Record<string, string>>({});

  async function mutate(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE" = "PUT", body?: object) {
    setBusy(path);
    setError("");
    try {
      await browserBackendMutation(path, method, body);
      router.refresh();
      return true;
    } catch (caught) {
      setError(caught instanceof BrowserBackendError ? caught.message : "Backend API unavailable. This change was not saved.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function patchControls(patch: AutonomousControlPatch) {
    const previous = controls;
    setBusy("autonomous-controls");
    setError("");
    try {
      await updateAutonomousControls(previous, patch, setControls);
      router.refresh();
      return true;
    } catch (caught) {
      setError(caught instanceof BrowserBackendError ? caught.message : "Backend API unavailable. This change was not saved.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function checkStatus(profile: ProfileSummary) {
    setProfileStatus((current) => ({ ...current, [profile.public_id]: "Checking…" }));
    try {
      const result = await browserBackendFetch<{ blocking_reasons?: unknown[]; autonomous_active?: boolean }>(`execution-profiles/${profile.public_id}/autonomy/status`);
      const reasons = Array.isArray(result.blocking_reasons) ? result.blocking_reasons.map(String) : [];
      setProfileStatus((current) => ({
        ...current,
        [profile.public_id]: result.autonomous_active ? "Autonomous active" : reasons.length ? `Blocked: ${reasons.map(displayValue).join(", ")}` : "Manual",
      }));
    } catch {
      setProfileStatus((current) => ({ ...current, [profile.public_id]: "Status unavailable" }));
    }
  }

  if (loadState === "unavailable") return null;
  if (!connections.length && !sectionErrors.connections) return <section className="empty-state workspace-empty"><div><div className="eyebrow">Broker workspace</div><h2>Connect TradeLocker to begin</h2><p>No stored connection was found. Add one to discover accounts and create execution profiles.</p></div><a className="button" href="/connect-tradelocker?new=1">Add connection</a></section>;

  const profiles = accounts.flatMap((account) => account.profiles);
  const enabledProfiles = profiles.filter((profile) => profile.enabled);
  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  const liveProfiles = accounts.filter((account) => account.environment === "live").flatMap((account) => account.profiles.filter((profile) => profile.enabled));

  return <>
    {error && <div className="error dashboard-alert" role="alert">{error}</div>}
    {Object.keys(sectionErrors).length>0&&<div className="notice dashboard-alert" role="status">Some dashboard sections are temporarily unavailable: {Object.keys(sectionErrors).join(", ")}. Available data is preserved.</div>}

    <section className="ops-grid" aria-label="Trading operations">
      <div className="ops-main">
        <section className="card control-center" aria-labelledby="automation-title">
          <header className="panel-header">
            <div><div className="eyebrow">Safety controls</div><h2 id="automation-title">Automation control center</h2><p>Backend-enforced controls for every autonomous submission.</p></div>
            <StatusBadge value={controls.global_autonomous_kill_switch ? "blocked" : "active"} label={controls.global_autonomous_kill_switch ? "Trading blocked" : "System armed"} />
          </header>
          <div className="control-list">
            <ControlRow title="Global kill switch" description="Immediately blocks all new autonomous demo and live submissions." value={controls.global_autonomous_kill_switch} onLabel="Enabled" offLabel="Off" dangerous disabled={Boolean(busy)} onChange={(value) => void patchControls({ global_autonomous_kill_switch: value })} />
            <ControlRow title="Demo automation" description="Runs enabled demo profiles according to their schedules and risk rules." value={controls.demo_autonomous_enabled} onLabel="Running" offLabel="Manual" disabled={Boolean(busy) || controls.global_autonomous_kill_switch} onChange={(value) => void patchControls({ demo_autonomous_enabled: value })} />
            <ControlRow title="Live automation" description={controls.live_execution_supported ? "Runs eligible profiles using real funds." : "Live execution is not supported by this deployment."} value={controls.live_autonomous_enabled} onLabel="Running live" offLabel="Disabled" dangerous disabled={Boolean(busy) || !controls.live_execution_supported || controls.global_autonomous_kill_switch} onChange={(value) => value ? setDialog({ kind: "live", confirmation: "" }) : void patchControls({ live_autonomous_enabled: false })} />
          </div>
          <footer className="panel-footer"><span>Effective demo: <strong>{displayValue(controls.effective.demo)}</strong></span><span>Effective live: <strong>{displayValue(controls.effective.live)}</strong></span><span>Updated {formatDate(controls.updated_at)}</span></footer>
        </section>

        <section className="accounts-workspace" aria-labelledby="accounts-title">
          <header className="section-heading compact-heading"><div><div className="eyebrow">Execution workspace</div><h2 id="accounts-title">Connections &amp; accounts</h2><p>Manage account context and the profiles bound to each TradeLocker account.</p></div><a className="button" href="/connect-tradelocker?new=1">Add connection</a></header>
          <div className="connection-list">{connections.map((connection) => {
            const owned = accounts.filter((account) => account.connection_id === connection.public_id);
            return <article className="card connection-card" key={connection.public_id}>
              <header className="connection-header"><div className="connection-title"><span className="broker-mark" aria-hidden="true">TL</span><div><h3>{connection.label || displayBroker(connection.broker_name || connection.server)}</h3><p>{displayBroker(connection.broker_name || connection.server)}</p></div></div><StatusBadge value={connection.enabled ? "connected" : "reauthentication_required"} /></header>
              <div className="connection-toolbar"><span>{owned.length} account{owned.length === 1 ? "" : "s"}</span><span>Verified {formatDate(connection.last_verified_at)}</span><div className="toolbar-actions"><button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate(`broker/tradelocker/discover-accounts?connection_id=${encodeURIComponent(connection.public_id)}`, "POST")}>Refresh</button><a className="button secondary" href={`/connect-tradelocker?connection_id=${encodeURIComponent(connection.public_id)}`}>Reauthenticate</a></div></div>
              <div className="account-stack">{owned.map((account) => <AccountCard key={account.public_id} account={account} schedules={schedules} busy={Boolean(busy)} profileStatus={profileStatus} checkStatus={checkStatus} mutate={mutate} openDialog={setDialog} />)}</div>
            </article>;
          })}</div>
        </section>
      </div>

      <aside className="ops-rail" aria-label="Operational summaries">
        <article className="card rail-card"><header className="rail-heading"><div><div className="eyebrow">Today UTC</div><h2>Decision flow</h2></div><StatusBadge value={workerHealth.status} /></header><div className="outcome-grid"><Metric label="Trade" value={dailySummary.outcomes.TRADE} tone="positive" /><Metric label="No trade" value={dailySummary.outcomes.NO_TRADE} /><Metric label="Blocked" value={dailySummary.outcomes.BLOCKED} tone="warning" /><Metric label="Errors" value={dailySummary.outcomes.ERROR} tone="negative" /></div><div className="rail-facts"><span><strong>{dailySummary.daily_entry_count}</strong> entries</span><span><strong>{dailySummary.armed_profiles}</strong> armed profiles</span></div></article>
        <article className="card rail-card"><header className="rail-heading"><div><div className="eyebrow">Scheduler</div><h2>Next runs</h2></div><span className="count-pill">{activeSchedules.length}</span></header><div className="timeline">{schedules.length ? schedules.slice(0, 5).map((schedule) => <div className="timeline-item" key={schedule.id}><span className={`timeline-dot ${schedule.enabled ? "is-active" : ""}`} /><div><strong>{profiles.find((item) => item.public_id === schedule.profile_ref)?.name || "Stored profile"}</strong><small>{schedule.enabled ? formatDate(schedule.next_run_at) : "Paused"}</small><small>{schedule.expression.times.join(", ")} · {schedule.timezone}</small></div></div>) : <p className="empty-copy">No schedules configured.</p>}</div></article>
        <article className="card rail-card"><header className="rail-heading"><div><div className="eyebrow">Activity</div><h2>Recent executions</h2></div><span className="count-pill">{executions.length}</span></header><div className="activity-list">{executions.length ? executions.slice(0, 6).map((item) => <div className="activity-item" key={item.id}><span className="activity-glyph" aria-hidden="true">{item.action_type.slice(0, 1).toUpperCase()}</span><div><strong>{displayValue(item.action_type)}</strong><small>{formatDate(item.created_at)}</small></div><StatusBadge value={item.state} /></div>) : <p className="empty-copy">No demo executions recorded.</p>}</div></article>
        <article className="rail-note"><span className="signal-dot" aria-hidden="true" /><p><strong>{enabledProfiles.length} profile{enabledProfiles.length === 1 ? "" : "s"} enabled.</strong> Position and pending-order data will appear here when an authenticated HTTP contract is available.</p></article>
      </aside>
    </section>

    <ActionDialog dialog={dialog} busy={Boolean(busy)} liveProfiles={liveProfiles} killSwitch={controls.global_autonomous_kill_switch} setDialog={setDialog} mutate={mutate} patchControls={patchControls} />
  </>;
}

function AccountCard({ account, schedules, busy, profileStatus, checkStatus, mutate, openDialog }: { account: AccountSummary; schedules: ScheduleSummary[]; busy: boolean; profileStatus: Record<string, string>; checkStatus: (profile: ProfileSummary) => Promise<void>; mutate: (path: string, method?: "POST" | "PUT" | "PATCH" | "DELETE", body?: object) => Promise<boolean>; openDialog: (dialog: Dialog) => void }) {
  return <article className={`account-card ${account.is_default_analysis ? "is-selected" : ""}`}>
    <header className="account-header"><div><div className="account-title-row"><h4>{account.account_alias}</h4>{account.is_default_analysis && <span className="selected-tag" data-status="selected_account">Selected</span>}</div><p>{account.account_name || `${displayBroker(account.broker_name)} account`} · {account.currency || "Currency unknown"}</p></div><div className="badges"><StatusBadge value={account.is_demo === 1 ? "demo" : account.is_demo === 0 ? "live" : "unknown"} /><StatusBadge value={account.available && account.locally_enabled ? "active" : "unavailable"} /></div></header>
    <div className="profile-table"><div className="profile-table-head"><span>Profile</span><span>Risk</span><span>Schedule</span><span>Status</span><span className="sr-only">Actions</span></div>{account.profiles.length ? account.profiles.map((profile) => {
      const schedule = schedules.find((item) => item.profile_ref === profile.public_id);
      return <div className="profile-table-row" key={profile.public_id}><div><strong>{profile.name}</strong><small>{displayStrategy(profile.strategy_name, profile.strategy_version)}</small></div><div><strong>{profile.risk?.risk_per_trade_percent === undefined ? "—" : `${profile.risk.risk_per_trade_percent}%`}</strong><small>{profile.risk?.maximum_open_positions === undefined ? "Backend managed" : `${profile.risk.maximum_open_positions} max open`}</small></div><div><strong>{schedule ? schedule.expression.times.join(", ") : "Not set"}</strong><small>{schedule ? schedule.timezone : "No schedule"}</small></div><div><StatusBadge value={profile.enabled ? "enabled" : "disabled"} />{profileStatus[profile.public_id] && <small>{profileStatus[profile.public_id]}</small>}</div><div className="row-actions"><button className="text-button" onClick={() => void checkStatus(profile)}>Verify</button><button className="text-button" onClick={() => openDialog({ kind: "edit", account, profile, name: profile.name, enabled: profile.enabled, allowedPairs: (profile.allowed_instruments || []).join(", ") })}>Edit</button></div></div>;
    }) : <div className="empty-row">No execution profiles attached.</div>}</div>
    <footer className="account-footer"><div className="actions compact"><button className="button" onClick={() => openDialog({ kind: "create", account, value: "" })}>Create profile</button><button className="button secondary" onClick={() => openDialog({ kind: "rename", account, value: account.account_alias })}>Rename</button>{!account.is_default_analysis && <button className="button secondary" disabled={busy} onClick={() => void mutate(`broker/accounts/${account.public_id}/default`)}>Select account</button>}</div></footer>
  </article>;
}

function ControlRow({ title, description, value, onLabel, offLabel, disabled, dangerous = false, onChange }: { title: string; description: string; value: boolean; onLabel: string; offLabel: string; disabled: boolean; dangerous?: boolean; onChange: (value: boolean) => void }) {
  return <div className="control-row"><div><strong>{title}</strong><p>{description}</p></div><label className={`switch ${dangerous ? "is-danger" : ""}`}><input type="checkbox" aria-label={title} checked={value} disabled={disabled} onChange={(event) => onChange(event.target.checked)} /><span className="switch-track"><span className="switch-thumb" /></span><span className="switch-label">{value ? onLabel : offLabel}</span></label></div>;
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "positive" | "warning" | "negative" }) {
  return <div className={`outcome-metric tone-${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function ActionDialog({ dialog, busy, liveProfiles, killSwitch, setDialog, mutate, patchControls }: { dialog: Dialog; busy: boolean; liveProfiles: ProfileSummary[]; killSwitch: boolean; setDialog: (dialog: Dialog) => void; mutate: (path: string, method?: "POST" | "PUT" | "PATCH" | "DELETE", body?: object) => Promise<boolean>; patchControls: (patch: AutonomousControlPatch) => Promise<boolean> }) {
  if (!dialog) return null;
  if (dialog.kind === "live") return <AppModal open title="Enable live autonomous trading" description="Live trading uses real funds. Confirm this change explicitly." onClose={() => setDialog(null)}><div className="modal-summary"><div><dt>Enabled live profiles</dt><dd>{liveProfiles.length}</dd></div><div><dt>Global kill switch</dt><dd>{killSwitch ? "Enabled" : "Off"}</dd></div></div><div className="field"><label htmlFor="live-confirmation">Type <strong>ENABLE LIVE AUTONOMY</strong></label><input id="live-confirmation" autoComplete="off" value={dialog.confirmation} onChange={(event) => setDialog({ ...dialog, confirmation: event.target.value })} /></div><div className="modal-actions"><button className="button secondary" onClick={() => setDialog(null)}>Cancel</button><button className="button danger-solid" disabled={busy || dialog.confirmation !== "ENABLE LIVE AUTONOMY"} onClick={async () => { if (await patchControls({ live_autonomous_enabled: true, live_confirmation: dialog.confirmation })) setDialog(null); }}>Enable live trading</button></div></AppModal>;

  if (dialog.kind === "delete") return <AppModal open title="Delete execution profile" description={`Delete ${dialog.profile.name}? Schedules will be detached and this cannot be undone.`} onClose={() => setDialog(null)}><div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button danger-solid" type="button" disabled={busy} onClick={async () => { const saved = await mutate(`execution-profiles/${dialog.profile.public_id}?confirmation_name=${encodeURIComponent(dialog.profile.name)}`, "DELETE"); if (saved) setDialog(null); }}>Delete profile</button></div></AppModal>;

  if (dialog.kind === "edit") return <AppModal open title="Edit execution profile" description={`Profile bound to ${dialog.account.account_alias}. Risk limits remain backend-authoritative.`} onClose={() => setDialog(null)}><form onSubmit={async (event) => { event.preventDefault(); const saved = await mutate(`execution-profiles/${dialog.profile.public_id}`, "PUT", { name: dialog.name.trim(), enabled: dialog.enabled, allowed_instruments: dialog.allowedPairs.split(",").map((value) => value.trim()).filter(Boolean) }); if (saved) setDialog(null); }}><div className="field"><label htmlFor="profile-name">Profile name</label><input id="profile-name" required maxLength={80} value={dialog.name} onChange={(event) => setDialog({ ...dialog, name: event.target.value })} /></div><div className="field"><label htmlFor="allowed-pairs">Allowed pairs</label><input id="allowed-pairs" value={dialog.allowedPairs} onChange={(event) => setDialog({ ...dialog, allowedPairs: event.target.value })} /></div><label className="toggle-row"><input type="checkbox" checked={dialog.enabled} onChange={(event) => setDialog({ ...dialog, enabled: event.target.checked })} /><span>Profile enabled</span></label><div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button></div><div className="destructive-zone"><h3>Danger zone</h3><p>Disabling preserves schedules and history. Deleting detaches schedules and cannot be undone.</p><div className="actions compact"><button className="button danger" type="button" disabled={busy} onClick={async () => { if (await mutate(`execution-profiles/${dialog.profile.public_id}`, "PUT", { enabled: false })) setDialog(null); }}>Disable profile</button><button className="button danger-solid" type="button" disabled={busy} onClick={() => setDialog({ kind: "delete", profile: dialog.profile })}>Delete profile</button></div></div></form></AppModal>;

  const isRename = dialog.kind === "rename";
  return <AppModal open title={isRename ? "Rename account" : "Create execution profile"} description={isRename ? "Use a clear alias that is easy to reference in ChatGPT." : `Create a profile bound to ${dialog.account.account_alias}.`} onClose={() => setDialog(null)}><form onSubmit={async (event) => { event.preventDefault(); const value = dialog.value.trim(); if (!value) return; const saved = isRename ? await mutate(`broker/accounts/${dialog.account.public_id}/alias`, "PUT", { alias: value }) : await mutate("execution-profiles", "POST", { name: value, account_id: dialog.account.public_id }); if (saved) setDialog(null); }}><div className="field"><label htmlFor="dialog-value">{isRename ? "Account alias" : "Profile name"}</label><input id="dialog-value" required maxLength={80} value={dialog.value} onChange={(event) => setDialog({ ...dialog, value: event.target.value })} /></div><div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button></div></form></AppModal>;
}
