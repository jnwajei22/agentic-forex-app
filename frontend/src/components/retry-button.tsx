"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export default function RetryButton() {
  const router = useRouter();
  const [retrying, startTransition] = useTransition();
  return (
    <button className="button secondary" type="button" disabled={retrying} onClick={() => {
      startTransition(() => router.refresh());
    }}>
      {retrying ? "Trying Again…" : "Try Again"}
    </button>
  );
}
