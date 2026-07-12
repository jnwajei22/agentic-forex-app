import { auth0 } from "@/lib/auth0";
import SettingsPanel from "./panel";

export default async function SettingsPage() {
  if (!(await auth0.getSession())) {
    return <main className="shell page"><div className="error">Not logged in.</div></main>;
  }
  return <main className="shell page"><div className="eyebrow">Account settings</div><h1 style={{ fontSize: 44 }}>TradeLocker connection</h1><SettingsPanel /></main>;
}
