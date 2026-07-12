import type { ReactNode } from "react";

export default function OnboardingShell({ eyebrow, title, children }: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return <main className="onboarding-shell">
    <section className="onboarding-panel">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      {children}
    </section>
  </main>;
}
