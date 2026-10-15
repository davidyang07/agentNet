"use client";

import { useRouter } from "next/navigation";

import { RunConfigurator } from "@/components/run/RunConfigurator";
import { PageHeader } from "@/components/shell/AppShell";
import { Spinner } from "@/components/ui/States";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { PRESETS } from "@/lib/experiment/presets";

/**
 * Step 1: describe the system under test and the attacks, then launch. This
 * screen has one job — the run itself opens in Watch.
 */
export default function SetupPage() {
  const { control, canStart, start, hydrating } = useExperiment();
  const router = useRouter();

  if (hydrating) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-fg-muted">
        <Spinner /> Restoring session…
      </div>
    );
  }

  const config = control.activeConfig;
  const runId = control.experimentId;

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Set up an assessment"
        description="Pick a preset or describe the system and the attacks, then launch. The run opens in Watch."
      />

      <div className="p-4 lg:p-5">
        <RunConfigurator
          disabled={!canStart}
          initialConfig={config ?? PRESETS[0].config}
          submitLabel={runId ? "Launch new assessment" : "Launch assessment"}
          footnote={
            runId &&
            (canStart
              ? "Replaces the current run in Watch, Results and Fix. It stays under Runs."
              : "Available again once the current run finishes.")
          }
          onStart={(next) => {
            // Launching moves the operator straight on to step 2, which shows
            // "Starting run…" until the backend has created it.
            start(next);
            router.push("/watch");
          }}
        />
      </div>
    </div>
  );
}
