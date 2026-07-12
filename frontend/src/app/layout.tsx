import type { Metadata } from "next";
import { auth0 } from "@/lib/auth0";
import Navigation from "./navigation";

import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic Forex Desk",
  description: "Connect your TradeLocker account to the Agentic Forex Desk MCP server.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const session = await auth0.getSession();
  return (
    <html lang="en">
      <body>
        <Navigation authenticated={Boolean(session)} />
        {children}
      </body>
    </html>
  );
}
