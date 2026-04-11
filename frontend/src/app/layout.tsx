import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Clinical Trial Matching Console",
  description: "Operational frontend for trial ingestion, review, and patient matching."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
