import assert from "node:assert/strict";
import test from "node:test";

import { loadDashboardData } from "./dashboard-data.ts";

const responses:Record<string,unknown>={
  "/api/broker/status":{status:"ready",connected:true,selected_account:{account_alias:"herofx-demo-1"}},
  "/api/broker/connections":{connections:[{public_id:"conn",server:"HeroFX",environment:"demo",enabled:true,account_count:1,is_default:true}]},
  "/api/broker/accounts":{accounts:[{public_id:"acct",account_alias:"herofx-demo-1",environment:"demo",available:true,locally_enabled:true,is_default_analysis:true,connection_id:"conn",profiles:[]}]},
  "/api/execution-profiles":{profiles:[{public_id:"profile",name:"AI",account_alias:"herofx-demo-1",execution_mode:"demo_autonomous",strategy_name:"adaptive",strategy_version:"2",enabled:true}]},
  "/api/autonomous-runs":{runs:[{run_id:"run",outcome:"NO_TRADE",status:"no_trade",started_at:"2026-07-18T00:00:00Z"}]},
  "/api/demo-executions":{executions:[]},"/api/autonomous-schedules":{schedules:[]},
  "/api/autonomous-worker-health":{status:"healthy",workers:[]},
  "/api/autonomous-daily-summary":{date:"2026-07-18",outcomes:{TRADE:0,NO_TRADE:1,BLOCKED:0,ERROR:0},daily_entry_count:0,kill_switch:false,armed_profiles:1},
  "/api/autonomous-controls":{global_autonomous_kill_switch:false,demo_autonomous_enabled:true,live_autonomous_enabled:false,live_execution_supported:false,updated_at:"",effective:{demo:"active",live:"manual"}},
};

test("real backend fixtures normalize into Dashboard V2 contracts",async()=>{
  const calls:string[]=[];const result=await loadDashboardData(async(path)=>{calls.push(path);return responses[path] as never;});
  assert.equal(result.connections[0].public_id,"conn");assert.equal(result.accounts[0].account_alias,"herofx-demo-1");
  assert.equal(result.profiles[0].public_id,"profile");assert.equal(result.executions[0].id,"run");
  assert.equal(result.coreUnavailable,false);assert.equal(calls.every(path=>path.startsWith("/api/")&&!/place|submit|cancel|close/.test(path)),true);
});

test("one optional endpoint failure preserves all successful dashboard data",async()=>{
  const result=await loadDashboardData(async(path)=>{
    if(path==="/api/autonomous-worker-health")throw {category:"server_error"};
    return responses[path] as never;
  });
  assert.equal(result.coreUnavailable,false);assert.equal(result.connections.length,1);assert.equal(result.accounts.length,1);
  assert.equal(result.errors.worker,"server_error");
});

test("global unavailable requires both core authenticated reads to fail",async()=>{
  const result=await loadDashboardData(async(path)=>{
    if(path==="/api/broker/status"||path==="/api/broker/connections")throw {category:"network"};
    return responses[path] as never;
  });
  assert.equal(result.coreUnavailable,true);assert.equal(result.profiles.length,1);
});
