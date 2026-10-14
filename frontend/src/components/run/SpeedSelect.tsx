"use client";

import { buttonClass } from "@/components/ui/Button";
import { IconChevronDown } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 4, 8] as const;

/**
 * Playback speed as one compact control. It is set once per run, so it does
 * not earn six buttons of permanent space. Shared by the live run bar and the
 * replay transport so the two never diverge.
 */
export function SpeedSelect({
  value,
  onChange,
  disabled,
  ariaLabel = "Playback speed",
  className,
}: {
  value: number;
  onChange: (speed: number) => void;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        aria-label={ariaLabel}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={buttonClass("default", "sm", "appearance-none pr-6 font-mono tabular")}
      >
        {SPEED_OPTIONS.map((multiplier) => (
          <option key={multiplier} value={multiplier}>
            {multiplier}×
          </option>
        ))}
      </select>
      <IconChevronDown className="pointer-events-none absolute right-1.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" />
    </div>
  );
}
