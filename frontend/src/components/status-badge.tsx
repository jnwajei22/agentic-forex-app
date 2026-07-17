import { statusLabel, statusTone } from "@/lib/status";

export default function StatusBadge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={`status-badge status-${statusTone(value)}`} data-tone={statusTone(value)}>
      {label ?? statusLabel(value)}
    </span>
  );
}
