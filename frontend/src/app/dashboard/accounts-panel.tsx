"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppModal from "@/components/app-modal";
import ScheduleModal, { type ScheduleValue } from "@/components/schedule-modal";
import StatusBadge from "@/components/status-badge";
import { displayBroker, displayStrategy, displayValue } from "@/lib/display";
import { BrowserBackendError, browserBackendFetch, browserBackendMutation, updateAutonomousControls, type AutonomousControls, type AutonomousControlPatch } from "@/lib/browser-backend";
import { displayedProviderReadiness, validateMinimumConfidence, type ProviderReadiness } from "@/lib/decision-engine";

export type ConnectionSummary = { public_id: string; label?: string; broker_name?: string; server: string; environment: string; enabled: boolean; account_count: number; last_verified_at?: string; is_default: boolean };
export type ProfileRisk = { risk_per_trade_percent?: number; daily_loss_limit_percent?: number; drawdown_cutoff_percent?: number; maximum_open_positions?: number; maximum_pending_orders?: number; maximum_new_entries_per_day?: number; minimum_reward_risk?: number };
export type ProfileSummary = { public_id: string; name: string; account_alias: string; execution_mode: string; strategy_name: string; strategy_version: string; strategy_template_id?: string; enabled: boolean; decision_provider?: "openai" | "no_trade"; model_identifier?: string | null; minimum_confidence?: number; provider_readiness?: ProviderReadiness; allowed_instruments?: string[]; risk?: ProfileRisk };
export type AccountSummary = { public_id: string; account_alias: string; account_name?: string; broker_name?: string; currency?: string; environment: string; is_demo?: number | null; available: boolean; locally_enabled: boolean; is_default_analysis: boolean; connection_id: string; profiles: ProfileSummary[] };
export type ScheduleSummary = { id: string; profile_ref: string; timezone: string; expression: { times: string[] }; enabled: boolean; next_run_at?: string; next_run_at_local?: string; last_run_at?: string; last_run_at_local?: string; last_run_status?: string; maximum_lateness_seconds: number; latest_dispatch?: { id: string; state: string; safe_retry: boolean; reason_code?: string; outcome?: string } };
export type WorkerHealth = { status: string; workers: Array<{ worker_id: string; status: string; last_heartbeat_at: string; healthy: boolean }> };
export type DailySummary = { date: string; outcomes: { TRADE: number; NO_TRADE: number; BLOCKED: number; ERROR: number }; daily_entry_count: number; kill_switch: boolean; armed_profiles: number };

type ConfirmDialog = { kind: "confirm"; title: string; description: string; action: () => Promise<void>; destructive?: boolean; expectedText?: string };
type RenameDialog = { kind: "rename"; account: AccountSummary; value: string };
type CreateDialog = { kind: "create"; account: AccountSummary; value: string };
type EditDialog = { kind: "edit"; account: AccountSummary; profile: ProfileSummary; draft: ProfileDraft };
type LiveDialog = { kind: "live"; confirmation: string };
type DialogState = ConfirmDialog | RenameDialog | CreateDialog | EditDialog | LiveDialog | null;
type ScheduleDialog = { account: AccountSummary; profile: ProfileSummary; current?: ScheduleSummary } | null;
type ProfileDraft = { name: string; enabled: boolean; strategyTemplateId: string; allowedPairs: string; decisionProvider: "openai" | "no_trade"; modelIdentifier: string; minimumConfidence: string; risk: Required<ProfileRisk> };

type Props = { loadState: "loaded" | "unavailable"; connections: ConnectionSummary[]; accounts: AccountSummary[]; profiles: ProfileSummary[]; executions: Array<{ id: string; action_type: string; state: string; created_at: string }>; schedules: ScheduleSummary[]; workerHealth: WorkerHealth; dailySummary: DailySummary; autonomousControls: AutonomousControls };

const riskDefaults: Required<ProfileRisk> = { risk_per_trade_percent: .25, daily_loss_limit_percent: 3, drawdown_cutoff_percent: 10, maximum_open_positions: 1, maximum_pending_orders: 1, maximum_new_entries_per_day: 2, minimum_reward_risk: 1.5 };

export default function AccountsPanel({ loadState, connections, accounts, executions, schedules, workerHealth, dailySummary, autonomousControls }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [profileStatus, setProfileStatus] = useState<Record<string, string>>({});
  const [dialog, setDialog] = useState<DialogState>(null);
  const [scheduleDialog, setScheduleDialog] = useState<ScheduleDialog>(null);
  const [controls, setControls] = useState(autonomousControls);

  async function mutate(path: string, method = "PUT", body?: object): Promise<boolean> {
    setBusy(path); setError("");
    try {
      await browserBackendMutation(path, method as "POST" | "PUT" | "PATCH" | "DELETE", body);
      router.refresh(); return true;
    } catch (caught) { setError(caught instanceof BrowserBackendError ? caught.message : "Backend API unavailable. This change was not saved."); return false; }
    finally { setBusy(null); }
  }

  async function patchControls(patch: AutonomousControlPatch): Promise<boolean> {
    const previous = controls;
    setBusy("autonomous-controls"); setError("");
    try {
      await updateAutonomousControls(previous, patch, setControls);
      router.refresh();
      return true;
    } catch (caught) {
      setError(caught instanceof BrowserBackendError ? caught.message : "Backend API unavailable. This change was not saved.");
      return false;
    } finally { setBusy(null); }
  }

  function confirm(title: string, description: string, action: () => Promise<void>, destructive = true, expectedText?: string) {
    setDialog({ kind: "confirm", title, description, action, destructive, expectedText });
  }

  function editProfile(account: AccountSummary, profile: ProfileSummary) {
    setDialog({ kind: "edit", account, profile, draft: { name: profile.name, enabled: profile.enabled, strategyTemplateId: profile.strategy_template_id || "strategy_hourly_forex_v1", allowedPairs: (profile.allowed_instruments || []).join(", "), decisionProvider: profile.decision_provider || "no_trade", modelIdentifier: profile.model_identifier || "", minimumConfidence: String(profile.minimum_confidence ?? .7), risk: { ...riskDefaults, ...profile.risk } } });
  }

  async function checkStatus(profile: ProfileSummary) {
    setProfileStatus(current => ({ ...current, [profile.public_id]: "Checking…" }));
    try {
      const body = await browserBackendFetch<{ blocking_reasons?: unknown[]; autonomous_active?: boolean }>(`execution-profiles/${profile.public_id}/autonomy/status`);
      const reasons = Array.isArray(body.blocking_reasons) ? body.blocking_reasons.map(String) : [];
      setProfileStatus(current => ({ ...current, [profile.public_id]: body.autonomous_active ? "Autonomous Active" : reasons.length ? `Blocked: ${reasons.map(displayValue).join(", ")}` : "Manual" }));
    } catch { setProfileStatus(current => ({ ...current, [profile.public_id]: "Status Unavailable" })); }
  }

  if (loadState === "unavailable") return <section className="management-section" aria-label="TradeLocker connections unavailable" />;
  if (!connections.length) return <section className="management-section empty-state"><div><div className="eyebrow">TradeLocker Connections</div><h2>No TradeLocker connections are configured.</h2><p>The backend verified that no stored connections exist.</p></div><a className="button" href="/connect-tradelocker?new=1">Add Connection</a></section>;

  const allProfiles = accounts.flatMap(account => account.profiles);
  const liveAccounts = accounts.filter(account => account.environment === "live");
  const liveProfiles = liveAccounts.flatMap(account => account.profiles.filter(profile => profile.enabled));
  const autonomousState = (account: AccountSummary, profile: ProfileSummary) => {
    if (!profile.enabled) return "profile_disabled";
    if (!account.available || !account.locally_enabled) return "unavailable";
    if (controls.global_autonomous_kill_switch) return "kill_switch_enabled";
    return account.environment === "demo" ? (controls.demo_autonomous_enabled ? "active" : "manual") : (controls.live_autonomous_enabled ? "blocked" : "manual");
  };

  return <>
    <section className="management-section">
      <article className="card operational-card">
        <div className="label">Autonomous Trading</div>
        {error && <div className="error" role="alert">{error}</div>}
        <ControlRow title="Global Autonomous Kill Switch" description="Blocks all new autonomous demo and live submissions. Manual activity remains available." value={controls.global_autonomous_kill_switch} onLabel="Kill Switch Enabled" offLabel="Kill Switch Off" disabled={Boolean(busy)} onChange={value => void patchControls({ global_autonomous_kill_switch: value })} />
        <ControlRow title="Demo Autonomous Trading" description="Allows enabled demo profiles to trade autonomously according to their schedules and risk rules." value={controls.demo_autonomous_enabled} onLabel="Demo Autonomous On" offLabel="Demo Autonomous Off" disabled={Boolean(busy)} onChange={value => void patchControls({ demo_autonomous_enabled: value })} />
        <ControlRow title="Live Autonomous Trading" description="Allows eligible live profiles to trade autonomously using real funds." value={controls.live_autonomous_enabled} onLabel="Live Autonomous On" offLabel="Live Autonomous Off" disabled={Boolean(busy)} onChange={value => value ? setDialog({ kind: "live", confirmation: "" }) : void patchControls({ live_autonomous_enabled: false })} />
        {!controls.live_execution_supported && <div className="error">Live execution path not yet available</div>}
        <small>Last updated: {controls.updated_at ? new Date(controls.updated_at).toLocaleString() : "Not yet changed"}</small>
      </article>

      <div className="section-heading"><div><div className="eyebrow">TradeLocker Connections</div><h2>Connections, Accounts, and Execution Profiles</h2><p>Profiles stay bound to one account. Environment controls determine whether they run manually or autonomously.</p></div><a className="button" href="/connect-tradelocker?new=1">Add Connection</a></div>
      <div className="connection-list">{connections.map(connection => {
        const owned = accounts.filter(account => account.connection_id === connection.public_id);
        return <article className="card connection-card" key={connection.public_id}>
          <header className="connection-header"><div><h3>{connection.label || displayBroker(connection.broker_name || connection.server)}</h3><p>{displayBroker(connection.broker_name || connection.server)}</p></div><StatusBadge value={connection.enabled ? "connected" : "reauthentication_required"} /></header>
          <div className="metadata"><span>Last verified: {connection.last_verified_at ? new Date(connection.last_verified_at).toLocaleString() : "Not yet verified"}</span><span>Account count: {owned.length}</span></div>
          <div className="actions compact"><button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate(`broker/tradelocker/discover-accounts?connection_id=${encodeURIComponent(connection.public_id)}`, "POST")}>Refresh Accounts</button><a className="button secondary" href={`/connect-tradelocker?connection_id=${encodeURIComponent(connection.public_id)}`}>Reauthenticate</a></div>
          <div className="account-stack">{owned.map(account => <article className="account-card" key={account.public_id}>
            <header className="account-header"><div><h4>{account.account_alias}</h4><p>{account.account_name || `${displayBroker(account.broker_name)} Account`}</p></div><div className="badges"><StatusBadge value={account.is_demo === 1 ? "demo" : account.is_demo === 0 ? "live" : "unknown"} /><StatusBadge value={account.available && account.locally_enabled ? "active" : "unavailable"} />{account.is_default_analysis && <StatusBadge value="selected_account" />}</div></header>
            <div className="metadata"><span>Currency: {account.currency || "Unknown"}</span></div>
            <div className="profile-list"><div className="label">Execution Profiles</div>{account.profiles.length ? account.profiles.map(profile => {
              const schedule = schedules.find(item => item.profile_ref === profile.public_id);
              const state = autonomousState(account, profile);
              return <div className="profile-row" key={profile.public_id}><div className="profile-copy"><strong>{profile.name}</strong><small>{account.account_alias} · {displayStrategy(profile.strategy_name, profile.strategy_version)}</small><div className="badges inline-badges"><StatusBadge value={profile.enabled ? "enabled" : "disabled"} /><StatusBadge value={state} label={state === "active" ? "Autonomous Active" : state === "manual" ? "Manual" : displayValue(state)} /></div><small>Decision Engine: {profile.decision_provider === "openai" ? "OpenAI" : "No Trade"}</small>{profile.model_identifier && <small>Model: {profile.model_identifier}</small>}<small>Risk per trade: {profile.risk?.risk_per_trade_percent ?? .25}% · Maximum open positions: {profile.risk?.maximum_open_positions ?? 1}</small><small>Schedule: {schedule ? `${schedule.enabled ? "Scheduled" : "Paused"} · ${schedule.expression.times.join(", ")} ${schedule.timezone}` : "Not configured"}</small><small>Latest run: {schedule?.latest_dispatch ? `${displayValue(schedule.latest_dispatch.state)}${schedule.latest_dispatch.reason_code ? ` · ${displayValue(schedule.latest_dispatch.reason_code)}` : ""}` : "No run yet"}</small>{profile.decision_provider === "no_trade" && <small className="error">Decision provider is configured for no-trade testing.</small>}{profileStatus[profile.public_id] && <small>{profileStatus[profile.public_id]}</small>}</div><div className="actions compact profile-actions"><button className="button secondary" onClick={() => void checkStatus(profile)}>Check Status</button><button className="button secondary" onClick={() => setScheduleDialog({ account, profile, current: schedule })}>Schedule</button><button className="button secondary" onClick={() => editProfile(account, profile)}>Edit Profile</button></div></div>;
            }) : <p>No execution profiles are attached to this account.</p>}</div>
            <div className="actions compact account-actions"><button className="button" onClick={() => setDialog({ kind: "create", account, value: `${account.account_alias} Hourly` })}>Create Profile</button><button className="button secondary" onClick={() => setDialog({ kind: "rename", account, value: account.account_alias })}>Rename Alias</button>{!account.is_default_analysis && <button className="button gold" onClick={() => void mutate(`broker/accounts/${account.public_id}/default`)}>Make Selected Account</button>}</div>
          </article>)}</div>
        </article>;
      })}</div>

      <article className="card operational-card"><div className="label">Autonomous Scheduler</div><div className="badges inline-badges"><StatusBadge value={workerHealth.status} /></div><p>Today UTC — Trade {dailySummary.outcomes.TRADE} · No Trade {dailySummary.outcomes.NO_TRADE} · Blocked {dailySummary.outcomes.BLOCKED} · Error {dailySummary.outcomes.ERROR} · Actual entries {dailySummary.daily_entry_count}</p>{schedules.length ? schedules.map(schedule => <div className="profile-row" key={schedule.id}><div><strong>{allProfiles.find(item => item.public_id === schedule.profile_ref)?.name || "Stored Profile"}</strong><small>{schedule.expression.times.join(", ")} {schedule.timezone}</small><small>Next: {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "Paused"} · Last: {schedule.last_run_status ? displayValue(schedule.last_run_status) : "No run yet"}</small></div><div className="actions compact"><button className="button secondary" onClick={() => void mutate(`autonomous-schedules/${schedule.id}/${schedule.enabled ? "pause" : "resume"}`, "POST")}>{schedule.enabled ? "Pause" : "Resume"}</button><button className="button danger" onClick={() => confirm("Delete Schedule", "Delete this schedule? Profile and execution history remain available.", async () => { await mutate(`autonomous-schedules/${schedule.id}`, "DELETE"); })}>Delete</button></div></div>) : <p>No autonomous schedules are configured.</p>}</article>
      <article className="card operational-card"><div className="label">Recent Demo Executions</div>{executions.length ? executions.map(item => <p key={item.id}><strong>{displayValue(item.action_type)}</strong> · {displayValue(item.state)} · {new Date(item.created_at).toLocaleString()}</p>) : <p>No demo executions have been recorded.</p>}</article>
    </section>

    <ActionDialog dialog={dialog} busy={Boolean(busy)} setDialog={setDialog} mutate={mutate} patchControls={patchControls} liveAccounts={liveAccounts} liveProfiles={liveProfiles} globalKillSwitch={controls.global_autonomous_kill_switch} confirm={confirm} />
    {scheduleDialog && <ScheduleModal key={scheduleDialog.profile.public_id} open profile={{ name: scheduleDialog.profile.name, accountAlias: scheduleDialog.account.account_alias, strategy: displayStrategy(scheduleDialog.profile.strategy_name, scheduleDialog.profile.strategy_version), executionMode: scheduleDialog.account.environment === "live" ? "Live" : "Demo" }} initial={{ timezone: scheduleDialog.current?.timezone, times: scheduleDialog.current?.expression.times, enabled: scheduleDialog.current?.enabled }} saving={Boolean(busy)} onClose={() => setScheduleDialog(null)} onSave={async (value: ScheduleValue) => { const saved = await mutate(`execution-profiles/${scheduleDialog.profile.public_id}/autonomy/schedule`, "POST", { ...value, maximum_lateness_seconds: 600 }); if (saved) setScheduleDialog(null); }} />}
  </>;
}

function ControlRow({ title, description, value, onLabel, offLabel, disabled, onChange }: { title: string; description: string; value: boolean; onLabel: string; offLabel: string; disabled: boolean; onChange: (value: boolean) => void }) {
  return <div className="profile-row"><div><strong>{title}</strong><p>{description}</p><StatusBadge value={value ? "active" : "manual"} label={value ? onLabel : offLabel} /></div><label className="toggle-row"><input aria-label={title} type="checkbox" checked={value} disabled={disabled} onChange={event => onChange(event.target.checked)} /><span>{value ? "On" : "Off"}</span></label></div>;
}

function ActionDialog({ dialog, busy, setDialog, mutate, patchControls, liveAccounts, liveProfiles, globalKillSwitch, confirm }: { dialog: DialogState; busy: boolean; setDialog: (dialog: DialogState) => void; mutate: (path: string, method?: string, body?: object) => Promise<boolean>; patchControls: (patch: AutonomousControlPatch) => Promise<boolean>; liveAccounts: AccountSummary[]; liveProfiles: ProfileSummary[]; globalKillSwitch: boolean; confirm: (title: string, description: string, action: () => Promise<void>, destructive?: boolean, expectedText?: string) => void }) {
  const [typed, setTyped] = useState("");
  const [decisionError, setDecisionError] = useState("");
  if (!dialog) return null;
  if (dialog.kind === "confirm") return <AppModal open title={dialog.title} description={dialog.description} onClose={() => setDialog(null)}>{dialog.expectedText && <div className="field"><label htmlFor="typed-confirmation">Type <strong>{dialog.expectedText}</strong> to confirm</label><input id="typed-confirmation" value={typed} onChange={event => setTyped(event.target.value)} /></div>}<div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className={dialog.destructive ? "button danger-solid" : "button"} disabled={busy || Boolean(dialog.expectedText && typed !== dialog.expectedText)} onClick={async () => { await dialog.action(); setDialog(null); }}>{busy ? "Saving…" : "Confirm"}</button></div></AppModal>;
  if (dialog.kind === "live") return <AppModal open title="Enable Live Autonomous Trading" description="Live trading uses real funds. The current repository has no live execution path, so runs will remain blocked." onClose={() => setDialog(null)}><div className="modal-summary"><p><strong>Affected accounts:</strong> {liveAccounts.map(item => item.account_alias).join(", ") || "None"}</p><p><strong>Enabled profiles:</strong> {liveProfiles.map(item => item.name).join(", ") || "None"}</p>{liveProfiles.map(item => <p key={item.public_id}><strong>{item.name} risk:</strong> {item.risk?.risk_per_trade_percent ?? .25}% per trade; max {item.risk?.maximum_open_positions ?? 1} open position</p>)}<p><strong>Global kill switch:</strong> {globalKillSwitch ? "Enabled" : "Off"}</p></div><div className="field"><label htmlFor="live-confirmation">Type <strong>ENABLE LIVE AUTONOMY</strong></label><input id="live-confirmation" value={dialog.confirmation} onChange={event => setDialog({ ...dialog, confirmation: event.target.value })} /></div><div className="modal-actions"><button className="button secondary" onClick={() => setDialog(null)}>Cancel</button><button className="button danger-solid" disabled={busy || dialog.confirmation !== "ENABLE LIVE AUTONOMY"} onClick={async () => { if (await patchControls({ live_autonomous_enabled: true, live_confirmation: dialog.confirmation })) setDialog(null); }}>Enable Live Autonomous Trading</button></div></AppModal>;

  const title = dialog.kind === "rename" ? "Rename Account Alias" : dialog.kind === "create" ? "Create Execution Profile" : "Edit Profile";
  return <AppModal open title={title} onClose={() => setDialog(null)}><form onSubmit={async event => { event.preventDefault(); let saved = false; if (dialog.kind === "rename") saved = Boolean(dialog.value.trim()) && await mutate(`broker/accounts/${dialog.account.public_id}/alias`, "PUT", { alias: dialog.value.trim() }); if (dialog.kind === "create") saved = Boolean(dialog.value.trim()) && await mutate("execution-profiles", "POST", { name: dialog.value.trim(), account_id: dialog.account.public_id }); if (dialog.kind === "edit") { const validation = validateMinimumConfidence(dialog.draft.minimumConfidence); if (validation) { setDecisionError(validation); return; } setDecisionError(""); saved = await mutate(`execution-profiles/${dialog.profile.public_id}`, "PUT", { name: dialog.draft.name, enabled: dialog.draft.enabled, strategy_template_id: dialog.draft.strategyTemplateId, allowed_instruments: dialog.draft.allowedPairs.split(",").map(value => value.trim()).filter(Boolean), decision_provider: dialog.draft.decisionProvider, model_identifier: dialog.draft.modelIdentifier.trim() || null, minimum_confidence: Number(dialog.draft.minimumConfidence), risk: dialog.draft.risk }); } if (saved) setDialog(null); }}>
    {(dialog.kind === "rename" || dialog.kind === "create") && <div className="field"><label htmlFor="dialog-value">{dialog.kind === "rename" ? "Account alias" : "Profile name"}</label><input id="dialog-value" required maxLength={80} value={dialog.value} onChange={event => setDialog({ ...dialog, value: event.target.value })} /></div>}
    {dialog.kind === "create" && <div className="modal-summary"><p><strong>Account:</strong> {dialog.account.account_alias}</p><p><strong>Environment:</strong> {dialog.account.environment}</p><p>Trading is manual until the environment autonomous control is enabled.</p></div>}
    {dialog.kind === "edit" && <EditFields dialog={dialog} setDialog={setDialog} decisionError={decisionError} />}
    <div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button></div>
    {dialog.kind === "edit" && <div className="destructive-zone"><h3>Danger Zone</h3><button className="button danger" type="button" onClick={() => confirm("Disable Profile", `Disable ${dialog.profile.name}? Schedules and history will be preserved.`, async () => { await mutate(`execution-profiles/${dialog.profile.public_id}`, "PUT", { enabled: false }); })}>Disable Profile</button><button className="button danger-solid" type="button" onClick={() => confirm("Delete Profile", `Delete ${dialog.profile.name}? Schedules will be detached and history preserved.`, async () => { await mutate(`execution-profiles/${dialog.profile.public_id}?confirmation_name=${encodeURIComponent(dialog.profile.name)}`, "DELETE"); }, true, dialog.profile.name)}>Delete Profile</button></div>}
  </form></AppModal>;
}

function EditFields({ dialog, setDialog, decisionError }: { dialog: EditDialog; setDialog: (dialog: DialogState) => void; decisionError: string }) {
  const updateRisk = (key: keyof ProfileRisk, value: number) => setDialog({ ...dialog, draft: { ...dialog.draft, risk: { ...dialog.draft.risk, [key]: value } } });
  const readiness = displayedProviderReadiness(dialog.draft.decisionProvider, dialog.draft.modelIdentifier, dialog.profile.provider_readiness);
  return <><div className="field"><label htmlFor="profile-name">Profile name</label><input id="profile-name" value={dialog.draft.name} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, name: event.target.value } })} /></div><div className="modal-summary"><p><strong>Bound account:</strong> {dialog.account.account_alias}</p><p><strong>Environment:</strong> {dialog.account.environment}</p><p><strong>Strategy version:</strong> {dialog.profile.strategy_version}</p></div><section className="modal-summary" aria-labelledby="decision-engine-heading"><h3 id="decision-engine-heading">Decision Engine</h3><div className="field"><label htmlFor="decision-provider">Decision Provider</label><select id="decision-provider" value={dialog.draft.decisionProvider} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, decisionProvider: event.target.value as "openai" | "no_trade" } })}><option value="openai">OpenAI</option><option value="no_trade">No Trade — Testing Only</option></select></div><p><strong>Provider readiness:</strong> <StatusBadge value={readiness.status} label={readiness.label} /></p>{dialog.draft.decisionProvider === "openai" ? <><div className="field"><label htmlFor="model-identifier">Model</label><input id="model-identifier" value={dialog.draft.modelIdentifier} placeholder="Configured OpenAI model identifier" onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, modelIdentifier: event.target.value } })} /></div><div className="field"><label htmlFor="minimum-confidence">Minimum Confidence</label><input id="minimum-confidence" type="number" required min="0" max="1" step="0.01" value={dialog.draft.minimumConfidence} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, minimumConfidence: event.target.value } })} /><small>Enter 0 to 1; for example, 0.70 means 70% confidence.</small></div></> : <p className="error">This testing provider always records a no-trade decision and will never submit an order.</p>}{decisionError && <div className="error" role="alert">{decisionError}</div>}</section><div className="field"><label htmlFor="strategy-template">Strategy</label><select id="strategy-template" value={dialog.draft.strategyTemplateId} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, strategyTemplateId: event.target.value } })}><option value="strategy_hourly_forex_v1">Hourly Forex</option><option value="strategy_ai_forex_confluence_v1">AI Forex Confluence</option></select></div><div className="field"><label htmlFor="allowed-pairs">Allowed pairs</label><input id="allowed-pairs" value={dialog.draft.allowedPairs} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, allowedPairs: event.target.value } })} /></div>{Object.entries({ risk_per_trade_percent: "Risk per trade", daily_loss_limit_percent: "Daily loss limit", drawdown_cutoff_percent: "Drawdown cutoff", maximum_open_positions: "Maximum open positions", maximum_pending_orders: "Maximum pending orders", maximum_new_entries_per_day: "Maximum new entries per day", minimum_reward_risk: "Minimum reward-to-risk" }).map(([key, label]) => <div className="field" key={key}><label htmlFor={key}>{label}</label><input id={key} type="number" step={key.includes("maximum_") ? 1 : .01} value={dialog.draft.risk[key as keyof ProfileRisk]} onChange={event => updateRisk(key as keyof ProfileRisk, Number(event.target.value))} /></div>)}<label className="toggle-row"><input type="checkbox" checked={dialog.draft.enabled} onChange={event => setDialog({ ...dialog, draft: { ...dialog.draft, enabled: event.target.checked } })} /><span>Profile enabled</span></label></>;
}
