import type { AutonomousControls } from "@/lib/browser-backend";
import type { AccountSummary, ConnectionSummary, DailySummary, ExecutionSummary, ProfileSummary, ScheduleSummary, WorkerHealth } from "@/lib/dashboard-contracts";

export type DashboardSection = "status"|"connections"|"accounts"|"profiles"|"runs"|"executions"|"schedules"|"worker"|"daily"|"controls";
export type DashboardRequest = <T>(path:string)=>Promise<T>;

const defaultControls:AutonomousControls={global_autonomous_kill_switch:true,demo_autonomous_enabled:false,
  live_autonomous_enabled:false,live_execution_supported:false,updated_at:"",effective:{demo:"blocked",live:"blocked"}};
const defaultDaily:DailySummary={date:"",outcomes:{TRADE:0,NO_TRADE:0,BLOCKED:0,MARKET_CLOSED:0,SKIPPED:0,ERROR:0},daily_entry_count:0,kill_switch:true,armed_profiles:0};

export type DashboardData={
  status:unknown|null;connections:ConnectionSummary[];accounts:AccountSummary[];profiles:ProfileSummary[];
  executions:ExecutionSummary[];schedules:ScheduleSummary[];workerHealth:WorkerHealth;
  dailySummary:DailySummary;autonomousControls:AutonomousControls;errors:Partial<Record<DashboardSection,string>>;
  coreUnavailable:boolean;
};

function message(reason:unknown):string {
  if (reason && typeof reason==="object" && "category" in reason) return String((reason as {category:unknown}).category);
  return "unknown";
}

export async function loadDashboardData(request:DashboardRequest):Promise<DashboardData> {
  const calls=[
    ["status","/api/broker/status"],["connections","/api/broker/connections"],["accounts","/api/broker/accounts"],
    ["profiles","/api/execution-profiles"],["runs","/api/autonomous-runs"],["executions","/api/demo-executions"],
    ["schedules","/api/autonomous-schedules"],["worker","/api/autonomous-worker-health"],
    ["daily","/api/autonomous-daily-summary"],["controls","/api/autonomous-controls"],
  ] as const;
  const settled=await Promise.allSettled(calls.map(([,path])=>request<unknown>(path)));
  const values:Partial<Record<DashboardSection,unknown>>={};const errors:Partial<Record<DashboardSection,string>>={};
  settled.forEach((result,index)=>{const key=calls[index][0];if(result.status==="fulfilled")values[key]=result.value;else errors[key]=message(result.reason);});
  const runRows=((values.runs as {runs?:Array<Record<string,unknown>>}|undefined)?.runs ?? []).map((run)=>({
    id:String(run.run_id ?? ""),action_type:String(run.outcome ?? "autonomous_decision"),state:String(run.status ?? "unknown"),
    created_at:String(run.started_at ?? run.completed_at ?? ""),
  })).filter((item)=>item.id);
  const legacyRows=(values.executions as {executions?:ExecutionSummary[]}|undefined)?.executions ?? [];
  return {
    status:values.status ?? null,
    connections:(values.connections as {connections?:ConnectionSummary[]}|undefined)?.connections ?? [],
    accounts:(values.accounts as {accounts?:AccountSummary[]}|undefined)?.accounts ?? [],
    profiles:(values.profiles as {profiles?:ProfileSummary[]}|undefined)?.profiles ?? [],
    executions:runRows.length?runRows:legacyRows,
    schedules:(values.schedules as {schedules?:ScheduleSummary[]}|undefined)?.schedules ?? [],
    workerHealth:(values.worker as WorkerHealth|undefined) ?? {status:"unavailable",workers:[]},
    dailySummary:(values.daily as DailySummary|undefined) ?? defaultDaily,
    autonomousControls:(values.controls as AutonomousControls|undefined) ?? defaultControls,
    errors,coreUnavailable:Boolean(errors.status && errors.connections),
  };
}
