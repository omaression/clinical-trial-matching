"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Command" },
  { href: "/trials", label: "Trials" },
  { href: "/review", label: "Review" },
  { href: "/patients", label: "Patients" },
  { href: "/pipeline", label: "Pipeline" }
] as const satisfies ReadonlyArray<{ href: Route; label: string }>;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-hero-radial">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 pb-16 pt-6 md:px-8">
        <div className="mb-8 flex flex-col gap-5 rounded-[32px] border border-ink/10 bg-white/70 px-5 py-5 shadow-card backdrop-blur md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.42em] text-tide">Clinical Trial Matching</p>
            <h1 className="text-2xl font-semibold text-ink">Operations Console</h1>
          </div>
          <nav className="flex flex-wrap gap-2">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    active ? "bg-ink text-sand" : "bg-sand/90 text-ink hover:bg-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <main className="flex-1 space-y-8">{children}</main>
      </div>
    </div>
  );
}
