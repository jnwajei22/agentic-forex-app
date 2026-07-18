export type ProfileRisk = {
  risk_per_trade_percent?: number;
  daily_loss_limit_percent?: number;
  drawdown_cutoff_percent?: number;
  maximum_open_positions?: number;
  maximum_pending_orders?: number;
  maximum_new_entries_per_day?: number;
  minimum_reward_risk?: number;
};

export type ProfileSummary = {
  public_id: string;
  name: string;
  account_alias: string;
  execution_mode: string;
  strategy_name: string;
  strategy_version: string;
  strategy_template_id?: string;
  enabled: boolean;
  allowed_instruments?: string[];
  risk?: ProfileRisk;
};

export type ConnectionSummary = {
  public_id: string;
  label?: string;
  broker_name?: string;
  server: string;
  environment: string;
  enabled: boolean;
  account_count: number;
  last_verified_at?: string;
  is_default: boolean;
};

export type AccountSummary = {
  public_id: string;
  account_alias: string;
  account_name?: string;
  broker_name?: string;
  currency?: string;
  environment: string;
  is_demo?: number | null;
  available: boolean;
  locally_enabled: boolean;
  is_default_analysis: boolean;
  connection_id: string;
  profiles: ProfileSummary[];
};

export type ScheduleSummary = {
  id: string;
  profile_ref: string;
  timezone: string;
  expression: { times: string[] };
  enabled: boolean;
  next_run_at?: string;
  next_run_at_local?: string;
  last_run_at?: string;
  last_run_at_local?: string;
  last_run_status?: string;
  maximum_lateness_seconds: number;
  latest_dispatch?: {
    id: string;
    state: string;
    safe_retry: boolean;
    reason_code?: string;
    outcome?: string;
  };
};

export type WorkerHealth = {
  status: string;
  workers: Array<{
    worker_id: string;
    status: string;
    last_heartbeat_at: string;
    healthy: boolean;
  }>;
};

export type DailySummary = {
  date: string;
  outcomes: { TRADE: number; NO_TRADE: number; BLOCKED: number; ERROR: number };
  daily_entry_count: number;
  kill_switch: boolean;
  armed_profiles: number;
};

export type ExecutionSummary = {
  id: string;
  action_type: string;
  state: string;
  created_at: string;
};
