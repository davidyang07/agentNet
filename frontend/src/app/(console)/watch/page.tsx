"use client";

import { useMemo } from "react";

import { EventFeed } from "@/components/activity/EventFeed";
import { TopologyWorkspace } from "@/components/graph/TopologyWorkspace";
import { OutbreakChart } from "@/components/insights/OutbreakChart";
import { PageHeader } from "@/components/shell/AppShell";
import { NextStepButton } from "@/components/shell/NextStep";
import { RequiresRun } from "@/components/shell/RequiresRun";
import { stepLabel } from "@/components/shell/nav";
import { SeverityDot } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { useSecurityInsights } from "@/lib/security/useSecurityInsights";
import { selectMetrics } from "@/lib/stream/reducer";
import { liveLogGapHint } from "@/lib/stream/sessionScope";
import { useOutbreakSeries } from "@/lib/stream/useOutbreakSeries";

export default function WatchPage() {
  return (
    <RequiresRun
      title="Nothing to watch yet"
      description="Launch an assessment in step 1 and it opens here: the security graph, coloured by compromise as it spreads, with every event as it happens."
    >
      {(experimentId) => <WatchContent experimentId={experimentId} />}
    </RequiresRun>
  );
}

/**
 * Step 2: one live view of the run. The graph is the hero; the outbreak curve
 * under it says how fast, the rail beside it says what just happened, and
 * selecting a node says why.
 */
function WatchContent({ experimentId }: { experimentId: string }) {
  const { control, stream } = useExperiment();
  const insights = useSecurityInsights(experimentId);
  const series = useOutbreakSeries(stream);
  const metrics = useMemo(() => selectMetrics(stream), [stream]);
  const events = stream.recentEvents;
  const eventGap = liveLogGapHint(control.status, events.length > 0);
  const curveGap = liveLogGapHint(control.status, series.length > 0);

  return (
    <div className="flex min-h-full flex-col xl:h-full">
      <PageHeader
        eyebrow={stepLabel("/watch")}
        title="Watch the attack"
        description="Colour is security state; shape is node type. Select a node to see how it was compromised and what it can reach."
        actions={<NextStepButton from="/watch" />}
        className="py-3"
      />

      <TopologyWorkspace
        experimentId={experimentId}
        stream={stream}
        securityGraph={insights.graph}
        blastRadius={insights.blastRadius}
        loading={insights.loading}
        belowGraph={
          <section aria-label="Outbreak progression" className="shrink-0 border-t border-line">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 pt-2.5">
              <h2 className="text-sm font-medium text-fg">Outbreak</h2>
              {/* The counts double as the chart's legend. */}
              <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                {[
                  { key: "compromised", label: "Compromised", value: metrics.compromised, severity: "critical" as const },
                  { key: "quarantined", label: "Quarantined", value: metrics.quarantined, severity: "contained" as const },
                  { key: "healthy", label: "Healthy", value: metrics.healthy, severity: "neutral" as const },
                ].map((item) => (
                  <li key={item.key} className="flex items-center gap-1.5">
                    <SeverityDot severity={item.severity} />
                    <span className="font-mono tabular text-fg">{item.value}</span>
                    <span className="text-fg-subtle">{item.label}</span>
                  </li>
                ))}
                <li className="text-fg-subtle">of {metrics.total} agents</li>
              </ul>
            </div>
            <div className="h-36 px-2 pb-1">
              <OutbreakChart
                series={series}
                maxTicks={control.activeConfig?.max_ticks ?? 200}
                emptyDescription={curveGap ?? "The curve builds as the simulation ticks."}
              />
            </div>
          </section>
        }
        liveRail={(selectNode) => (
          <EventFeed
            compact
            events={events}
            onSelectAgent={selectNode}
            className="min-h-0 flex-1"
            emptyTitle={eventGap ? "No events in this session" : "No events yet"}
            emptyHint={eventGap ?? "Events appear as soon as the first tick is published."}
            emptyAction={
              eventGap ? (
                <ButtonLink size="sm" href={`/history/${experimentId}`}>
                  Replay the full log
                </ButtonLink>
              ) : undefined
            }
          />
        )}
      />
    </div>
  );
}
