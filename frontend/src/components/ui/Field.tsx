"use client";

import { useId, type InputHTMLAttributes, type ReactNode } from "react";

import { IconChevronDown } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

// Inputs sit inset: one surface step *down* from the panel they live on.
const CONTROL =
  "h-8 w-full rounded-md border border-line-strong bg-surface px-2.5 text-sm text-fg " +
  "transition-colors duration-100 placeholder:text-fg-subtle " +
  "hover:border-fg-subtle/60 focus:border-accent focus:outline-none " +
  "disabled:cursor-not-allowed disabled:opacity-40";

function FieldFrame({
  id,
  label,
  hint,
  children,
  className,
}: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="text-xs font-medium text-fg-muted">
        {label}
      </label>
      {children}
      {hint && <p className="text-2xs text-fg-subtle">{hint}</p>}
    </div>
  );
}

export function NumberField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <FieldFrame id={id} label={label} hint={hint} className={className}>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        className={cn(CONTROL, "text-right font-mono tabular")}
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </FieldFrame>
  );
}

export function TextField({
  label,
  hint,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label?: ReactNode; hint?: ReactNode }) {
  const id = useId();
  const input = (
    <input id={id} type="text" className={cn(CONTROL, !label && className)} {...rest} />
  );
  if (!label) return input;
  return (
    <FieldFrame id={id} label={label} hint={hint} className={className}>
      {input}
    </FieldFrame>
  );
}

export function SelectField<T extends string>({
  label,
  hint,
  value,
  options,
  onChange,
  disabled,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <FieldFrame id={id} label={label} hint={hint} className={className}>
      <div className="relative">
        <select
          id={id}
          className={cn(CONTROL, "appearance-none pr-7")}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value as T)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <IconChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" />
      </div>
    </FieldFrame>
  );
}

/** Switch-style boolean, sized to sit on the same 32px row as the other controls. */
export function ToggleField({
  label,
  hint,
  checked,
  onChange,
  disabled,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex min-w-0 cursor-pointer select-none items-center gap-2.5 rounded-md border border-line-strong bg-surface px-2.5 py-1.5",
        "transition-colors duration-100 hover:border-fg-subtle/60",
        disabled && "cursor-not-allowed opacity-40 hover:border-line",
        className,
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        aria-hidden
        className={cn(
          "relative h-4 w-7 shrink-0 rounded-full transition-colors duration-150",
          "peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-accent",
          checked ? "bg-accent" : "bg-line-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 size-3 rounded-full bg-fg transition-[left] duration-150",
            checked ? "left-3.5" : "left-0.5",
          )}
        />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-medium text-fg">{label}</span>
        {hint && <span className="block text-2xs text-fg-subtle">{hint}</span>}
      </span>
    </label>
  );
}

/** Multi-select rendered as toggle chips — used for attack scenario selection,
 * where seeing every option at once matters more than saving space. */
export function ChipMultiSelect<T extends string>({
  options,
  selected,
  onToggle,
  disabled,
  ariaLabel,
}: {
  options: ReadonlyArray<{ value: T; label: string; hint?: string }>;
  selected: readonly T[];
  onToggle: (value: T) => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  return (
    <div role="group" aria-label={ariaLabel} className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const active = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            title={option.hint}
            disabled={disabled}
            onClick={() => onToggle(option.value)}
            className={cn(
              "h-7 rounded-md border px-2.5 text-xs font-medium transition-colors duration-100",
              "disabled:cursor-not-allowed disabled:opacity-40",
              active
                ? "border-accent-line bg-accent-soft text-fg"
                : "border-line-strong bg-surface text-fg-muted hover:border-fg-subtle/60 hover:text-fg",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
