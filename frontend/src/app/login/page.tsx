import { redirect } from "next/navigation";

import { auth0 } from "@/lib/auth0";

export default async function LoginPage() {
  if (await auth0.getSession()) redirect("/dashboard");
  return (
    <main className="shell page">
      <section className="card" style={{ maxWidth: 520, margin: "50px auto" }}>
        <div className="eyebrow">Secure access</div>
        <h2 style={{ marginTop: 12 }}>Log in with Auth0</h2>
        <p>Your session stays in encrypted, HTTP-only cookies managed by the frontend server.</p>
        <a className="button" href="/auth/login?returnTo=/dashboard">Continue to Auth0</a>
      </section>
    </main>
  );
}
