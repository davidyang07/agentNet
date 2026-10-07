"use client";

import type { ReactNode } from "react";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, Spinner } from "@/components/ui/States";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";

/**
 * Guard for screens that only mean something while a run exists. Renders a
 * route-specific empty state rather than a blank screen — the previous
 * dashboard showed an empty void before the first Start.
 */
export function RequiresRun({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: (experimentId: string) => ReactNode;
}) {
  const { control, hydrating } = useExperiment();

  if (hydrating) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-fg-muted">
        <Spinner /> Restoring session…
      </div>
    );
  }

  // A launch from step 1 lands here before the backend has created the run.
  if (control.pending === "start") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-fg-muted">
        <Spinner /> Starting run…
      </div>
    );
  }

  if (!control.experimentId) {
    return (
      <EmptyState
        className="h-full"
        title={title}
        description={description}
        action={
          <ButtonLink href="/setup" variant="primary" size="sm">
            Go to step 1: Set up
          </ButtonLink>
        }
      />
    );
  }

  return <>{children(control.experimentId)}</>;
}
