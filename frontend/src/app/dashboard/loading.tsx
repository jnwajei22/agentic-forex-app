export default function DashboardLoading() {
  return <main className="dashboard-page" aria-busy="true">
    <div className="shell dashboard-shell">
      <header className="dashboard-hero"><div><div className="eyebrow">Operations desk</div><h1>Trading command center</h1><p>Loading your authenticated broker workspace.</p></div></header>
      <section className="overview-strip" aria-label="Loading workspace overview">{Array.from({ length: 4 }).map((_, index) => <article className="overview-card" key={index}><div className="overview-icon">0{index + 1}</div><div><span>Checking status</span><strong>Loading…</strong></div></article>)}</section>
      <section className="ops-grid"><div className="ops-main"><article className="card control-center"><header className="panel-header"><div><div className="eyebrow">Safety controls</div><h2>Loading controls</h2></div></header><div className="control-row"><p>Verifying backend-enforced autonomous trading state…</p></div></article></div><aside className="ops-rail"><article className="card rail-card"><div className="eyebrow">Today UTC</div><h2>Loading activity</h2></article></aside></section>
    </div>
  </main>;
}
