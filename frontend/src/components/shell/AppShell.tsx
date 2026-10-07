"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { RunContextBar } from "@/components/shell/RunContextBar";
import { ARCHIVE, isActivePath, WORKFLOW, type WorkflowStep } from "@/components/shell/nav";
import { BrandMark, IconHistory } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";

/**
 * Workspace chrome: the workflow as a numbered rail on the left, a
 * run-context bar across the top, and the screen itself scrolling underneath.
 * The live WebSocket lives above this in ExperimentProvider, so moving between
 * steps never interrupts a running assessment.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { control } = useExperiment();
  const hasRun = Boolean(control.experimentId);

  return (
    <div className="flex h-dvh min-h-0 w-full overflow-hidden bg-canvas">
      {/* Sidebar on the canvas, content in an inset surface beside it — the
          Linear shell (design-refs/shell.png). */}
      <nav aria-label="Primary" className="hidden w-56 shrink-0 flex-col lg:flex">
        <Link href="/" className="flex items-center gap-2.5 px-5 pb-2 pt-4 text-fg">
          <BrandMark className="size-5 shrink-0" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">AgentShield</span>
            <span className="block truncate text-2xs text-fg-subtle">Adversarial resilience</span>
          </span>
        </Link>

        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 py-4">
          <div>
            <p className="eyebrow px-2 pb-1">Assessment</p>
            <ol className="flex flex-col gap-px">
              {WORKFLOW.map((step, index) => (
                <li key={step.href} className="relative">
                  {/* The hairline joining the markers is what reads as a
                      sequence rather than a menu. */}
                  {index < WORKFLOW.length - 1 && (
                    <span aria-hidden className="absolute left-4.5 top-6.5 h-3.25 w-px bg-line-strong" />
                  )}
                  <StepLink
                    step={step}
                    active={isActivePath(pathname, step.href)}
                    locked={step.needsRun && !hasRun}
                  />
                </li>
              ))}
            </ol>
          </div>

          <div>
            <p className="eyebrow px-2 pb-1">Archive</p>
            <Link
              href={ARCHIVE.href}
              title={ARCHIVE.summary}
              aria-current={isActivePath(pathname, ARCHIVE.href) ? "page" : undefined}
              className={cn(
                "group flex h-8 items-center gap-2.5 rounded-sm px-2 transition-colors duration-100",
                isActivePath(pathname, ARCHIVE.href)
                  ? "bg-overlay text-fg"
                  : "text-fg-muted hover:bg-raised hover:text-fg",
              )}
            >
              <IconHistory className="size-4 shrink-0 text-fg-subtle group-hover:text-fg-muted" />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{ARCHIVE.label}</span>
            </Link>
          </div>
        </div>

        <p className="px-5 py-4 text-2xs text-fg-subtle">
          Deterministic simulation. Results are reproducible from{" "}
          <span className="font-mono">(seed, config)</span> — not real-world security evidence.
        </p>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col lg:py-2 lg:pr-2">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface lg:rounded-lg lg:border lg:border-line">
          {/* Archive screens are about a *persisted* run; showing the live run's
              status and transport beside a replay of a different run is the kind
              of ambiguity that makes an operator distrust the whole screen. */}
          {!pathname.startsWith("/history") && <RunContextBar />}

          {/* Below `lg` the rail becomes a horizontal strip of the same steps,
              so the nav never eats a third of a narrow viewport. */}
          <nav
            aria-label="Primary"
            className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 py-1.5 lg:hidden"
          >
            {WORKFLOW.map((step) => {
              const active = isActivePath(pathname, step.href);
              return (
                <Link
                  key={step.href}
                  href={step.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-8 shrink-0 items-center gap-1.5 rounded-sm px-2 text-xs font-medium transition-colors",
                    active ? "bg-overlay text-fg" : "text-fg-muted hover:bg-raised hover:text-fg",
                  )}
                >
                  <StepNumber step={step.step} active={active} />
                  {step.label}
                </Link>
              );
            })}
            <Link
              href={ARCHIVE.href}
              aria-current={isActivePath(pathname, ARCHIVE.href) ? "page" : undefined}
              className={cn(
                "flex h-8 shrink-0 items-center gap-1.5 rounded-sm px-2 text-xs font-medium transition-colors",
                isActivePath(pathname, ARCHIVE.href)
                  ? "bg-overlay text-fg"
                  : "text-fg-muted hover:bg-raised hover:text-fg",
              )}
            >
              <IconHistory className="size-3.5 text-fg-subtle" />
              {ARCHIVE.label}
            </Link>
          </nav>

          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </div>
  );
}

function StepLink({
  step,
  active,
  locked,
}: {
  step: WorkflowStep;
  active: boolean;
  /** The step needs a run and there isn't one yet. Still clickable — its
   * screen says what to do — but visibly not the next thing to do. */
  locked: boolean;
}) {
  return (
    <Link
      href={step.href}
      aria-current={active ? "page" : undefined}
      title={locked ? `${step.summary} Launch a run first.` : step.summary}
      className={cn(
        "group flex h-8 items-center gap-2.5 rounded-sm px-2 transition-colors duration-100",
        active
          ? "bg-overlay text-fg"
          : locked
            ? "text-fg-subtle hover:bg-raised"
            : "text-fg-muted hover:bg-raised hover:text-fg",
      )}
    >
      <StepNumber step={step.step} active={active} />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{step.label}</span>
    </Link>
  );
}

/** The step's number in a ring; the accent marks where the operator is. */
function StepNumber({ step, active }: { step: number; active: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative flex size-5 shrink-0 items-center justify-center rounded-full border text-2xs font-semibold tabular",
        active
          ? "border-transparent bg-accent text-on-accent"
          : "border-line-strong bg-canvas text-fg-subtle",
      )}
    >
      {step}
    </span>
  );
}

/** Standard screen header. Every workspace screen opens with one, so titles,
 * descriptions and screen-level actions line up across the product. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        <h1 className="text-xl font-semibold text-fg">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-xs text-fg-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
