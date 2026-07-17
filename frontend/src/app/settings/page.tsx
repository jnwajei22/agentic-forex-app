import { auth0 } from "@/lib/auth0";
import SettingsPanel from "./panel";

export default async function SettingsPage() {
  if (!(await auth0.getSession())) {
    return <main className="shell page"><div className="error">Not logged in.</div></main>;
  }
  return <main className="shell page"><div className="eyebrow">Account Settings</div><h1 className="page-title">Settings</h1><SettingsPanel /></main>;
}
