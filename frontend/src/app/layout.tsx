import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";

import { ExperimentProvider } from "@/lib/experiment/ExperimentProvider";

import "./globals.css";

// Inter is the Linear-recommended substitute (DESIGN.md › Typography); Geist
// Mono carries identifiers, ticks and log values.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AgentShield — Multi-Agent Adversarial Resilience",
  description:
    "Map agent systems, run adversarial scenarios, watch compromise propagate, compare defenses, trace causality, and validate remediation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* Browser extensions routinely add attributes to <body> before React
          hydrates; without this every page logs a hydration mismatch that has
          nothing to do with this app. */}
      <body className="h-full" suppressHydrationWarning>
        {/* The provider sits above both the landing page and the console
            shell, so the live WebSocket — and the run it is watching —
            survive navigation between every screen. */}
        <ExperimentProvider>{children}</ExperimentProvider>
      </body>
    </html>
  );
}
