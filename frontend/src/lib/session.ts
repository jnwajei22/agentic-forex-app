import { redirect } from "next/navigation";

import { auth0 } from "@/lib/auth0";

export async function requireSession() {
  const session = await auth0.getSession();
  if (!session) redirect("/login");
  return session;
}
