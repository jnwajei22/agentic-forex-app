import { requireSession } from "@/lib/session";
import ConnectTradeLockerForm from "./form";

export default async function ConnectTradeLockerPage() {
  await requireSession();
  return <main className="shell page"><div className="eyebrow">Broker onboarding</div><h1 style={{ fontSize: 44 }}>Connect TradeLocker</h1><p>Credentials are sent once to the encrypted Raspberry Pi backend. They are never stored in browser storage.</p><ConnectTradeLockerForm /></main>;
}
