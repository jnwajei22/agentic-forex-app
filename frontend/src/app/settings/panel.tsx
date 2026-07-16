"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { backendErrorMessage } from "@/lib/backend-error-message";
import { displayValue } from "@/lib/display";
import { parseTradeLockerStatus, type TradeLockerStatus } from "@/lib/tradelocker-status";

export default function SettingsPanel() {
  const router=useRouter(); const [status,setStatus]=useState<TradeLockerStatus|null>(null); const [error,setError]=useState(""); const [loading,setLoading]=useState(true); const [deleting,setDeleting]=useState(false);
  useEffect(()=>{fetch("/api/backend/broker/status").then(async response=>{const body=await response.json();if(!response.ok)throw {status:response.status,code:body.code};setStatus(parseTradeLockerStatus(body));}).catch(caught=>setError(typeof caught==="object"&&caught!==null&&"status" in caught?backendErrorMessage(caught as {status:number;code?:string}):"Backend API unavailable. Is the FastAPI server running?")).finally(()=>setLoading(false));},[]);
  async function disconnect(){if(!window.confirm("Disable this TradeLocker connection? Its accounts and profile history will be preserved."))return;setDeleting(true);setError("");const response=await fetch("/api/backend/broker/tradelocker",{method:"DELETE"}).catch(()=>null);if(!response?.ok){setError("Unable to disable TradeLocker.");setDeleting(false);return;}router.push("/dashboard");router.refresh();}
  if(loading)return <div className="notice">Loading TradeLocker settings…</div>;
  return <section className="card" style={{maxWidth:680}}>{error&&<div className="error">{error}</div>}{status?.status==="not_connected"&&<div className="notice">TradeLocker setup required.</div>}<div className="label">Connection Status</div><div className="value">{displayValue(status?.status)}</div>{status?.selected_account&&<div className="notice"><strong>Default Account: {status.selected_account.account_alias??"Configured"}</strong><p>Execution modes are managed on profiles bound to a specific stored account. Changing the Default Account never changes a profile binding.</p><Link className="button secondary" href="/dashboard">Manage Execution Profiles</Link></div>}<div className="actions"><Link className="button" href="/connect-tradelocker">Update Credentials</Link>{status?.status==="connected_no_account"&&<Link className="button secondary" href="/select-account">Choose Default Account</Link>}{status&&status.status!=="not_connected"&&<button className="button danger" onClick={disconnect} disabled={deleting}>{deleting?"Disabling…":"Disable Connection"}</button>}</div></section>;
}
