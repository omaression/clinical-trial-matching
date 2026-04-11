import type { ReactNode } from "react";

type StructuredPrimitive = string | number | boolean | null;

export type StructuredValue =
  | StructuredPrimitive
  | StructuredValue[]
  | { [key: string]: StructuredValue };

function isDefined<T>(value: T | undefined): value is T {
  return value !== undefined;
}

function toStructuredValue(value: unknown): StructuredValue | undefined {
  if (value === undefined || typeof value === "function" || typeof value === "symbol") {
    return undefined;
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (Array.isArray(value)) {
    return value.map(toStructuredValue).filter(isDefined);
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => {
        const normalized = toStructuredValue(nested);
        return normalized === undefined ? undefined : ([key, normalized] as const);
      })
      .filter(isDefined);
    return Object.fromEntries(entries);
  }
  return String(value);
}

function labelize(key: string): string {
  return key
    .replaceAll("_", " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPrimitive(value: StructuredPrimitive): string {
  if (value === null || value === "") {
    return "Unavailable";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

function hasRenderableValue(value: StructuredValue): boolean {
  if (value === null || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some(hasRenderableValue);
  }
  if (typeof value === "object") {
    return Object.values(value).some(hasRenderableValue);
  }
  return true;
}

function renderValue(value: StructuredValue): ReactNode {
  if (value === null || value === "") {
    return <span className="text-ink/45">Unavailable</span>;
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="text-ink">{formatPrimitive(value)}</span>;
  }

  if (Array.isArray(value)) {
    const items = value.filter(hasRenderableValue);
    if (!items.length) {
      return <span className="text-ink/45">Unavailable</span>;
    }
    if (items.every((item) => typeof item !== "object" || item === null)) {
      return (
        <div className="flex flex-wrap gap-2">
          {items.map((item, index) => (
            <span
              key={`${formatPrimitive(item as StructuredPrimitive)}-${index}`}
              className="rounded-full bg-sand px-3 py-1 text-sm text-ink/75"
            >
              {formatPrimitive(item as StructuredPrimitive)}
            </span>
          ))}
        </div>
      );
    }
    return (
      <div className="grid gap-3">
        {items.map((item, index) => (
          <div key={index} className="rounded-2xl border border-ink/8 bg-sand/50 p-4">
            {renderValue(item)}
          </div>
        ))}
      </div>
    );
  }

  const entries = Object.entries(value).filter(([, nested]) => hasRenderableValue(nested));
  if (!entries.length) {
    return <span className="text-ink/45">Unavailable</span>;
  }
  return (
    <dl className="grid gap-3 md:grid-cols-2">
      {entries.map(([key, nested]) => (
        <div key={key} className="rounded-2xl border border-ink/8 bg-sand/45 p-4">
          <dt className="text-xs font-semibold uppercase tracking-[0.22em] text-ink/45">{labelize(key)}</dt>
          <dd className="mt-2 text-sm leading-7 text-ink/72">{renderValue(nested)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function StructuredDataView({
  data,
  emptyLabel = "No structured data available."
}: {
  data: unknown;
  emptyLabel?: string;
}) {
  const normalized = toStructuredValue(data);
  if (!normalized || !hasRenderableValue(normalized)) {
    return <p className="text-sm leading-7 text-ink/68">{emptyLabel}</p>;
  }

  if (typeof normalized !== "object" || Array.isArray(normalized)) {
    return <div className="rounded-3xl border border-ink/8 bg-white/70 p-5">{renderValue(normalized)}</div>;
  }

  const entries = Object.entries(normalized).filter(([, value]) => hasRenderableValue(value));
  if (!entries.length) {
    return <p className="text-sm leading-7 text-ink/68">{emptyLabel}</p>;
  }

  return (
    <div className="grid gap-4">
      {entries.map(([key, value]) => (
        <section key={key} className="rounded-3xl border border-ink/8 bg-white/70 p-5">
          <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-tide">{labelize(key)}</h3>
          <div className="mt-4">{renderValue(value)}</div>
        </section>
      ))}
    </div>
  );
}
