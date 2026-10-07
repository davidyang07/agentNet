"use client";

import { useMemo } from "react";

import {
  AttackSurfacePanel,
  CriticalNodesPanel,
  ObservedCountersPanel,
} from "@/components/insights/Panels";
import { MetricsList, PostureTiles } from "@/components/insights/SecurityMetrics";
import { PageHeader } from "@/components/shell/AppShell";
import { NextStepButton, NextStepCard } from "@/components/shell/NextStep";
import { RequiresRun } from "@/components/shell/RequiresRun";
import { stepLabel } from "@/components/shell/nav";
import { ConfigChip } from "@/components/ui/Badge";
import { Panel, PanelDivider, PanelHeader } from "@/components/ui/Panel";
import { Disclaimer, ErrorState, StatListSkeleton } from "@/components/ui/States";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { useSecurityInsights } from "@/lib/security/useSecurityInsights";
import { selectMetrics } from "@/lib/stream/reducer";
import { configLabel } from "@/lib/vocabulary";

// Config fields worth restating next to the numbers they explain — the run's
// reproducibility surface, not the whole model.
const PROVENANCE_FIELDS = [
  "seed",
  "node_count",
  "edge_density",
  "software_type_count",
  "p_same",
  "p_cross",
  "detector_sensitivity",
  "defense_enabled",
  "max_ticks",
] as const;

export default function ResultsPage() {
  return (
    <RequiresRun
      title="No results yet"
      description="Results are computed from a running or completed assessment. Launch one in step 1."
    >
      {(experimentId) => <ResultsContent experimentId={experimentId} />}
    </RequiresRun>
  );
}

/**
 * Step 3: the verdict. Read top to bottom — the four headline numbers, every
 * metric with the definition it is computed from, then what the attacker
 * could reach and where containing it would matter most.
 */
function ResultsContent({ experimentId }: { experimentId: string }) {
  const { control, stream } = useExperiment();
  const insights = useSecurityInsights(experimentId);
  const counters = useMemo(() => selectMetrics(stream), [stream]);
  const config = control.activeConfig;

  return (
    <div className="flex flex-col">
      <PageHeader
        eyebrow={stepLabel("/results")}
        title="Results"
        description="How far compromise spread, and what the defense cost in retained utility. Every number is computed by the backend from this run's state and event log."
        actions={<NextStepButton from="/results" />}
      />

      <div className="flex flex-col gap-4 p-4 lg:p-5">
        {insights.error && <ErrorState title="Could not load results" detail={insights.error} />}

        {insights.metrics ? (
          <PostureTiles metrics={insights.metrics} />
        ) : (
          <Panel>
            <StatListSkeleton rows={2} />
          </Panel>
        )}

        <div className="grid gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <PanelHeader
              title="All metrics"
              description="Each with the definition the backend computes it from."
            />
            {insights.metrics ? (
              <MetricsList metrics={insights.metrics} withDefinitions />
            ) : (
              <StatListSkeleton rows={9} />
            )}
            <div className="mt-3 border-t border-line pt-3">
              <Disclaimer>
                Attack success rate, false-quarantine rate and both latencies are computed over
                the live event buffer, which is bounded — a long run&apos;s earliest events may
                have aged out. Replaying a persisted run computes them over its complete log.
              </Disclaimer>
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Run summary" description="What the live stream observed." />
            <ObservedCountersPanel metrics={counters} />
            {config && (
              <>
                <PanelDivider label="Configuration" />
                <p className="mb-2 text-xs text-fg-subtle">
                  Re-running with this seed and config reproduces every number on this page.
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {PROVENANCE_FIELDS.map((field) => (
                    <ConfigChip key={field} label={configLabel(field)} value={String(config[field])} />
                  ))}
                  {(config.active_scenarios ?? []).map((scenario) => (
                    <ConfigChip key={scenario} label="scenario" value={scenario} />
                  ))}
                </div>
              </>
            )}
          </Panel>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Panel>
            <PanelHeader
              title="Attack surface"
              description="Typed non-agent nodes, and how many the attacker took."
            />
            <AttackSurfacePanel graph={insights.graph} />
          </Panel>
          <Panel>
            <PanelHeader
              title="Choke points"
              description="Highest betweenness centrality — containing these disconnects the most."
            />
            <CriticalNodesPanel nodes={insights.criticalNodes} graph={insights.graph} />
          </Panel>
        </div>

        <NextStepCard from="/results" />

        <Disclaimer>
          Simulation results only — reproducible from{" "}
          <span className="font-mono">(seed, config)</span>, but not real-world security evidence
          about any deployed system.
        </Disclaimer>
      </div>
    </div>
  );
}
