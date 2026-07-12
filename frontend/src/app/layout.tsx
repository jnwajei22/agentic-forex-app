import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic Forex Desk",
  description: "TradeLocker-connected forex charting and market analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <nav className="nav">
          <div className="shell nav-inner">
            <Link className="brand" href="/">Agentic Forex Desk</Link>
            <div className="nav-links">
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/settings">Settings</Link>
              <a className="button secondary" href="/auth/logout">Log out</a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
