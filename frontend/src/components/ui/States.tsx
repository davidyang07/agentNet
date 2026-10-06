import type { ReactNode } from "react";

import { IconAlert, IconInfo } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

/**
 * Empty state. Always says what would fill this space and how to get there —
 * a bare "no data" is the single fastest way to make a product feel unfinished.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-1.5 px-4 py-6" : "gap-2 px-6 py-12",
        className,
      )}
    >
      {icon && <div className="mb-1 text-fg-subtle">{icon}</div>}
      <p className={cn("font-medium text-fg-muted", compact ? "text-xs" : "text-sm")}>{title}</p>
      {description && (
        <p className="max-w-sm text-xs leading-5 text-fg-subtle">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  detail,
  action,
  className,
}: {
  title?: string;
  detail?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-critical-line bg-critical-soft px-3 py-2.5",
        className,
      )}
    >
      <IconAlert className="mt-px size-3.5 shrink-0 text-critical" />
      <div className="flex min-w-0 flex-col gap-1.5">
        <p className="text-xs font-medium text-fg">{title}</p>
        {detail && <p className="break-words font-mono text-2xs text-fg-muted">{detail}</p>}
        {action && <div className="mt-1">{action}</div>}
      </div>
    </div>
  );
}

export function WarningBanner({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-warn-line bg-warn-soft px-3 py-2.5 text-xs leading-5 text-fg",
        className,
      )}
    >
      <IconAlert className="mt-0.5 size-3.5 shrink-0 text-warn" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Non-blocking caveat used wherever simulated results could be mistaken for
 * real-world evidence. Quiet by design — it must not compete with the data. */
export function Disclaimer({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-1.5 text-2xs text-fg-subtle">
      <IconInfo className="mt-0.5 size-3 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-sm bg-overlay motion-safe:animate-pulse", className)} />
  );
}

export function StatListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2.5 py-1">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center justify-between gap-4">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="h-3 w-10" />
        </div>
      ))}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block size-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent",
        className,
      )}
    />
  );
}
