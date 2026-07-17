export default function DashboardLoading() {
  return (
    <main className="shell page" aria-busy="true">
      <div className="eyebrow">Dashboard</div>
      <h1 className="page-title">Welcome back.</h1>
      <div className="notice">Loading TradeLocker connections…</div>
      <div className="notice">Checking account status…</div>
    </main>
  );
}
