const STATUS_STYLES: Record<string, string> = {
  healthy: "bg-moss/15 text-moss border-moss/30",
  degraded: "bg-ember/15 text-ember border-ember/30",
  eligible: "bg-moss/15 text-moss border-moss/30",
  possible: "bg-brass/15 text-brass border-brass/30",
  ineligible: "bg-ember/15 text-ember border-ember/30",
  completed: "bg-moss/15 text-moss border-moss/30",
  failed: "bg-ember/15 text-ember border-ember/30",
  running: "bg-tide/15 text-tide border-tide/30",
  pending: "bg-brass/15 text-brass border-brass/30",
  accepted: "bg-moss/15 text-moss border-moss/30",
  corrected: "bg-tide/15 text-tide border-tide/30",
  rejected: "bg-ember/15 text-ember border-ember/30",
  recruiting: "bg-tide/15 text-tide border-tide/30"
};

export function StatusPill({ value }: { value: string }) {
  const key = value.toLowerCase();
  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${
        STATUS_STYLES[key] ?? "border-ink/10 bg-ink/5 text-ink/70"
      }`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
