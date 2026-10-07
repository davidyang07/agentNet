import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";

/** Every workflow step and the run archive share the console chrome; the
 * landing page at `/` sits outside it. */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
