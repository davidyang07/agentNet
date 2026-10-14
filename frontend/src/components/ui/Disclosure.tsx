import type { ReactNode } from "react";

import { IconChevronRight } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

/**
 * The one way a screen reveals secondary detail: a quiet text button whose
 * chevron turns when open. Each screen shows its answer first; definitions,
 * tuning parameters and unchanged rows sit behind one of these.
 */
export function DisclosureButton({
  open,
  onToggle,
  children,
  className,
}: {
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      onClick={onToggle}
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium text-fg-subtle transition-colors duration-100 hover:text-fg-muted",
        className,
      )}
    >
      <IconChevronRight
        className={cn("size-3.5 shrink-0 transition-transform duration-100", open && "rotate-90")}
      />
      {children}
    </button>
  );
}
