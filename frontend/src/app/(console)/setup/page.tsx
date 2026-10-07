"use client";

import { useRouter } from "next/navigation";

import { RunConfigurator } from "@/components/run/RunConfigurator";
import { PageHeader } from "@/components/shell/AppShell";
import { stepLabel } from "@/components/shell/nav";
import { Badge, RunStatusBadge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { IconArrowRight } from "@/components/ui/icons";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { Spinner } from "@/components/ui/States";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { DEFAULT_CONFIG } from "@/lib/experiment/presets";
import { shortId } from "@/lib/format";
import { scenarioMeta } from "@/lib/vocabulary";

/**
 * Step 1: describe the system under test and the attacks, then launch. This
 * screen has one job — the run itself opens in Watch.
 */
export default function SetupPage() {
  const { control, stream, canStart, start, hydrating } = useExperiment();
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
        eyebrow={stepLabel("/setup")}
        title="Set up an assessment"
        description="Describe the system under test and the attacks to run against it, then launch. The run opens in Watch as soon as it starts."
      />

      <div className="flex flex-col gap-4 p-4 lg:p-5">
        {runId && config && (
          <Panel>
            <PanelHeader
              title="Current run"
              description={
                canStart
                  ? "Launching a new assessment replaces it in steps 2–4; it stays under Runs."
                  : "Launch is available again once this run finishes."
              }
              actions={
                <>
                  <ButtonLink href="/watch" size="sm">
                    Watch
                    <IconArrowRight className="size-3.5" />
                  </ButtonLink>
                  <ButtonLink href="/results" size="sm">
                    Results
                    <IconArrowRight className="size-3.5" />
                  </ButtonLink>
                </>
              }
            />
            <div className="flex flex-wrap items-center gap-2">
              <RunStatusBadge status={control.status} />
              <span className="font-mono text-xs text-fg" title={runId}>
                {shortId(runId)}
              </span>
              <span className="font-mono text-2xs tabular text-fg-subtle">
                t{stream.tick}/{config.max_ticks}
              </span>
              {(config.active_scenarios ?? []).map((scenario) => (
                <Badge key={scenario}>{scenarioMeta(scenario).label}</Badge>
              ))}
            </div>
          </Panel>
        )}

        <RunConfigurator
          disabled={!canStart}
          initialConfig={config ?? DEFAULT_CONFIG}
          submitLabel={runId ? "Launch new assessment" : "Launch assessment"}
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
