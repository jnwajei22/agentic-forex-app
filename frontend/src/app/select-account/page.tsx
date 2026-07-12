import { requireSession } from "@/lib/session";
import AccountSelector from "./selector";

export default async function SelectAccountPage() {
  await requireSession();
  return <main className="shell page"><div className="eyebrow">Broker onboarding</div><h1 style={{ fontSize: 44 }}>Select an account</h1><p>Choose which TradeLocker account this workspace should use for read-only charts and analysis.</p><AccountSelector /></main>;
}
