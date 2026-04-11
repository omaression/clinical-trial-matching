export function formatDate(value?: string | null): string {
  if (!value) {
    return "Unavailable";
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: value.includes("T") ? "short" : undefined
  }).format(new Date(value));
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function titleize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
