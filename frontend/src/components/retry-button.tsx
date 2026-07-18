"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export default function RetryButton({ label = "Restore Backend Connection" }: { label?: string }) {
  const router = useRouter();
  const [retrying, startTransition] = useTransition();
  return (
    <button className="button secondary" type="button" disabled={retrying} onClick={() => {
      startTransition(() => router.refresh());
    }}>
      {retrying ? "Restoring Backend Connection…" : label}
    </button>
  );
}
