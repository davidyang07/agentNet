"use client";

import { useMemo, useState } from "react";

import {
  AttackSurfacePanel,
  CriticalNodesPanel,
  ObservedCountersPanel,
} from "@/components/insights/Panels";
import {
  MetricsList,
  PostureTiles,
  SECONDARY_METRIC_KEYS,
} from "@/components/insights/SecurityMetrics";
import { PageHeader } from "@/components/shell/AppShell";
import { NextStepButton } from "@/components/shell/NextStep";
import { RequiresRun } from "@/components/shell/RequiresRun";
import { ConfigChip } from "@/components/ui/Badge";
import { DisclosureButton } from "@/components/ui/Disclosure";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { Disclaimer, ErrorState, StatListSkeleton } from "@/components/ui/States";
import type { ExperimentConfig } from "@/lib/api/client";
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

// The top few are the actionable ones; the rest of the ranking is noise here.
const CHOKE_POINTS_SHOWN = 5;

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
 * Step 3: the verdict. The four headline numbers, then the rest of the
 * metrics, what the attacker took, and where containing it matters most —
 * one row. Definitions and the run's provenance open on demand.
 */
function ResultsContent({ experimentId }: { experimentId: string }) {
  const { control, stream } = useExperiment();
  const insights = useSecurityInsights(experimentId);
  const counters = useMemo(() => selectMetrics(stream), [stream]);
  const config = control.activeConfig;
  const [showDefinitions, setShowDefinitions] = useState(false);
  const [showRunDetails, setShowRunDetails] = useState(false);

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Results"
        description="How far compromise spread, and what the defense cost."
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

        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Panel>
            <PanelHeader
              title="Other metrics"
              actions={
                <DisclosureButton
                  open={showDefinitions}
                  onToggle={() => setShowDefinitions((v) => !v)}
                >
                  Definitions
                </DisclosureButton>
              }
            />
            {insights.metrics ? (
              <MetricsList
                metrics={insights.metrics}
                keys={SECONDARY_METRIC_KEYS}
                withDefinitions={showDefinitions}
              />
            ) : (
              <StatListSkeleton rows={6} />
            )}
            {showDefinitions && (
              <div className="mt-3 border-t border-line pt-3">
                <Disclaimer>
                  Attack success rate, false-quarantine rate and both latencies are computed over
                  the live event buffer, which is bounded — a long run&apos;s earliest events may
                  have aged out. Replaying a persisted run computes them over its complete log.
                </Disclaimer>
              </div>
            )}
          </Panel>

          <Panel>
            <PanelHeader title="Attack surface" description="Non-agent nodes the attacker took." />
            <AttackSurfacePanel graph={insights.graph} />
          </Panel>

          <Panel className="lg:col-span-2 xl:col-span-1">
            <PanelHeader title="Choke points" description="Containing these disconnects the most." />
            <CriticalNodesPanel
              nodes={insights.criticalNodes.slice(0, CHOKE_POINTS_SHOWN)}
              graph={insights.graph}
            />
          </Panel>
        </div>

        {config && (
          <Panel>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <DisclosureButton
                open={showRunDetails}
                onToggle={() => setShowRunDetails((v) => !v)}
              >
                Run details
              </DisclosureButton>
              {!showRunDetails && (
                <span className="font-mono text-2xs text-fg-subtle">{runSummary(config)}</span>
              )}
            </div>
            {showRunDetails && (
              <div className="mt-3 grid gap-x-8 gap-y-4 lg:grid-cols-2">
                <div>
                  <h3 className="eyebrow mb-1">Observed in this session</h3>
                  <ObservedCountersPanel metrics={counters} />
                </div>
                <div>
                  <h3 className="eyebrow mb-1">Configuration</h3>
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
                </div>
              </div>
            )}
          </Panel>
        )}

        <Disclaimer>
          Simulation results only — reproducible from{" "}
          <span className="font-mono">(seed, config)</span>, but not real-world security evidence
          about any deployed system.
        </Disclaimer>
      </div>
    </div>
  );
}

/** The run's identity in one line, shown while its details are closed. */
function runSummary(config: ExperimentConfig): string {
  const scenarios = config.active_scenarios?.length ?? 0;
  return [
    `seed ${config.seed}`,
    `${config.node_count} agents`,
    `defense ${config.defense_enabled ? "on" : "off"}`,
    `${scenarios} scenario${scenarios === 1 ? "" : "s"}`,
  ].join(" · ");
}
