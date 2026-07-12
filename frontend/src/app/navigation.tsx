"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ONBOARDING_PATHS = new Set([
  "/onboarding",
  "/connect-tradelocker",
  "/select-account",
  "/setup-complete",
]);

export default function Navigation({ authenticated }: { authenticated: boolean }) {
  const pathname = usePathname();
  if (ONBOARDING_PATHS.has(pathname)) return null;
  return <nav className="nav">
    <div className="shell nav-inner">
      <Link className="brand" href="/">Agentic Forex Desk</Link>
      <div className="nav-links">
        {authenticated ? <>
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/settings">Settings</Link>
          <a className="button secondary" href="/auth/logout">Log out</a>
        </> : <a className="button" href="/auth/login?returnTo=/dashboard">Log in</a>}
      </div>
    </div>
  </nav>;
}
