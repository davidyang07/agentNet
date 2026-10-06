import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import {
  RUN_STATUS_LABEL,
  RUN_STATUS_SEVERITY,
  SECURITY_STATE_LABEL,
  SECURITY_STATE_SEVERITY,
  SEVERITY_BG,
  type RunStatus,
  type SecurityState,
  type Severity,
} from "@/lib/severity";

/**
 * Status badge: a neutral pill whose dot is the only colour (DESIGN.md ›
 * Components). The label stays in ink, so the state reads by word as well as
 * by hue — never by colour alone.
 */
export function Badge({
  severity = "neutral",
  children,
  className,
  title,
  dot = severity !== "neutral",
  pulse,
}: {
  severity?: Severity;
  children: ReactNode;
  className?: string;
  title?: string;
  /** Show the state dot. Defaults to on for every non-neutral severity. */
  dot?: boolean;
  pulse?: boolean;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-5 items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-overlay px-2 text-2xs font-medium text-fg-muted",
        className,
      )}
    >
      {dot && <SeverityDot severity={severity} pulse={pulse} />}
      {children}
    </span>
  );
}

export function SeverityDot({
  severity,
  pulse,
  className,
}: {
  severity: Severity;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex size-2 shrink-0", className)}>
      <span className={cn("size-2 rounded-full", SEVERITY_BG[severity])} />
      {pulse && (
        <span
          className={cn(
            "absolute inset-0 rounded-full opacity-60",
            SEVERITY_BG[severity],
            "motion-safe:animate-ping",
          )}
        />
      )}
    </span>
  );
}

export function SecurityStateBadge({ state }: { state: SecurityState }) {
  return <Badge severity={SECURITY_STATE_SEVERITY[state]}>{SECURITY_STATE_LABEL[state]}</Badge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge severity={RUN_STATUS_SEVERITY[status]} pulse={status === "running"}>
      {RUN_STATUS_LABEL[status]}
    </Badge>
  );
}

/** Compact key/value chip used for run configuration summaries in the top bar. */
export function ConfigChip({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="inline-flex h-5 items-center gap-1.5 whitespace-nowrap rounded-xs border border-line bg-overlay px-1.5">
      <span className="text-2xs text-fg-subtle">{label}</span>
      <span className="font-mono text-2xs text-fg">{value}</span>
    </span>
  );
}
