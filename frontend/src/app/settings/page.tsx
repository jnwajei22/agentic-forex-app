import { requireSession } from "@/lib/session";
import SettingsPanel from "./panel";

export default async function SettingsPage() {
  await requireSession();
  return <main className="shell page"><div className="eyebrow">Account settings</div><h1 style={{ fontSize: 44 }}>Broker connection</h1><SettingsPanel /></main>;
}
