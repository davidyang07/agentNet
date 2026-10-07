"use client";

import { ArmStatusCard } from "@/components/insights/ArmStatusCard";
import { FindingsList } from "@/components/insights/FindingsList";
import { MetricsDeltaTable } from "@/components/insights/MetricsComparison";
import { PageHeader } from "@/components/shell/AppShell";
import { RequiresRun } from "@/components/shell/RequiresRun";
import { stepLabel } from "@/components/shell/nav";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { Disclaimer, ErrorState, Spinner, StatListSkeleton } from "@/components/ui/States";
import type { ExperimentConfig } from "@/lib/api/client";
import { useComparison } from "@/lib/comparison/useComparison";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { formatConfigDiff } from "@/lib/format";
import { useFixTrial } from "@/lib/remediation/useFixTrial";
import { useSecurityInsights } from "@/lib/security/useSecurityInsights";

export default function FixPage() {
  return (
    <RequiresRun
      title="Nothing to fix yet"
      description="Fixes are derived from a run's security graph and metrics. Launch an assessment in step 1."
    >
      {(experimentId) => <FixContent experimentId={experimentId} />}
    </RequiresRun>
  );
}

/**
 * Step 4: change something and prove it mattered. Both sections answer the
 * same question the same way — run two configurations to completion from the
 * same seed and compare every metric — one for a proposed fix, one for the
 * defense itself.
 */
function FixContent({ experimentId }: { experimentId: string }) {
  const { control } = useExperiment();
  const config = control.activeConfig;

  return (
    <div className="flex flex-col">
      <PageHeader
        eyebrow={stepLabel("/fix")}
        title="Fix & re-test"
        description="Each finding is a concrete configuration change with a causal reason behind it. Re-testing runs the current and the changed configuration to completion from the same seed, then compares every metric."
      />

      <div className="flex flex-col gap-4 p-4 lg:p-5">
        <FindingsSection experimentId={experimentId} config={config} />
        <DefenseCheckSection config={config} />

        <Disclaimer>
          A re-test is evidence about this simulated configuration under this seed, not a
          guarantee about a deployed system. Re-run with several seeds before treating an
          improvement as robust.
        </Disclaimer>
      </div>
    </div>
  );
}

function FindingsSection({
  experimentId,
  config,
}: {
  experimentId: string;
  config: ExperimentConfig | null;
}) {
  const insights = useSecurityInsights(experimentId);
  const trial = useFixTrial();
  const count = insights.remediation?.recommendations.length ?? 0;

  return (
    <>
      {insights.error && <ErrorState title="Could not load findings" detail={insights.error} />}

      <Panel>
        <PanelHeader
          title="Findings"
          description="Configuration changes that would have changed this run's outcome."
          actions={
            insights.remediation && (
              <Badge severity={count > 0 ? "warn" : "ok"}>
                {count} finding{count === 1 ? "" : "s"}
              </Badge>
            )
          }
        />
        {insights.remediation ? (
          <FindingsList
            recommendations={insights.remediation.recommendations}
            baseConfig={config}
            validatingKey={trial.running ? trial.diffKey : null}
            disabled={trial.running || !config}
            onValidate={(diff) => {
              if (config) trial.validate(config, diff);
            }}
          />
        ) : (
          <StatListSkeleton rows={3} />
        )}

        {/* The re-test result belongs to the finding it tests, so it opens
            here, under the list, once one is started. */}
        {trial.diffKey && (
          <div className="mt-4 overflow-hidden rounded-md border border-line bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
              <span className="text-xs font-medium text-fg">
                Re-test:{" "}
                <span className="font-mono text-fg-muted">
                  {formatConfigDiff(JSON.parse(trial.diffKey) as Record<string, unknown>)}
                </span>
              </span>
              {trial.running && (
                <span className="flex items-center gap-1.5 text-2xs text-fg-muted">
                  <Spinner /> Running before and after
                </span>
              )}
            </div>
            {trial.before.status === "error" && (
              <ErrorState className="m-3" title="Before arm failed" detail={trial.before.error} />
            )}
            {trial.after.status === "error" && (
              <ErrorState className="m-3" title="After arm failed" detail={trial.after.error} />
            )}
            <MetricsDeltaTable
              before={trial.before.status === "done" ? trial.before.metrics : null}
              after={trial.after.status === "done" ? trial.after.metrics : null}
              beforeLabel="Before fix"
              afterLabel="After fix"
              withDefinitions={false}
            />
          </div>
        )}
      </Panel>
    </>
  );
}

function DefenseCheckSection({ config }: { config: ExperimentConfig | null }) {
  const { armA, armB, runComparison } = useComparison();
  const running = armA.status === "running" || armB.status === "running";
  const started = armA.status !== "idle" || armB.status !== "idle";

  return (
    <Panel>
      <PanelHeader
        title="Is the defense worth it?"
        description="Runs this configuration twice — defense off, then on — with everything else held constant, so any difference is the defense's doing."
        actions={
          <Button
            variant="primary"
            size="sm"
            disabled={running || !config}
            onClick={() => config && runComparison(config)}
          >
            {running ? "Running both…" : started ? "Run again" : "Run defense check"}
          </Button>
        }
      />
      {started && (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <ArmStatusCard inset label="Defense off" hint="Control" arm={armB} />
            <ArmStatusCard inset label="Defense on" hint="Treatment" arm={armA} />
          </div>
          <div className="overflow-hidden rounded-md border border-line bg-surface">
            <MetricsDeltaTable
              before={armB.status === "done" ? (armB.metrics ?? null) : null}
              after={armA.status === "done" ? (armA.metrics ?? null) : null}
              beforeLabel="Defense off"
              afterLabel="Defense on"
              withDefinitions={false}
            />
          </div>
        </div>
      )}
    </Panel>
  );
}
