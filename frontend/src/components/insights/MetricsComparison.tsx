"use client";

import {
  formatMetric,
  METRIC_DESCRIPTORS,
  metricSeverity,
  type MetricDescriptor,
} from "@/components/insights/SecurityMetrics";
import { SeverityDot } from "@/components/ui/Badge";
import { Td, TableWrap, Th, Tr } from "@/components/ui/Table";
import { cn } from "@/lib/cn";
import type { MetricsResponse } from "@/lib/api/client";

/** Whether a *decrease* in this metric is an improvement. */
function lowerIsBetter(descriptor: MetricDescriptor): boolean {
  return descriptor.kind !== "health";
}

export type DeltaDirection = "better" | "worse" | "same" | "unknown";

export function deltaDirection(
  descriptor: MetricDescriptor,
  before: number | null,
  after: number | null,
): DeltaDirection {
  if (before === null || after === null) return "unknown";
  if (before === after) return "same";
  const decreased = after < before;
  return decreased === lowerIsBetter(descriptor) ? "better" : "worse";
}

function formatDelta(descriptor: MetricDescriptor, before: number | null, after: number | null) {
  if (before === null || after === null) return "—";
  const diff = after - before;
  if (diff === 0) return "no change";
  const sign = diff > 0 ? "+" : "−";
  const magnitude = Math.abs(diff);
  if (descriptor.kind === "count") return `${sign}${magnitude}`;
  if (descriptor.kind === "latency") return `${sign}${magnitude.toFixed(1)} ticks`;
  return `${sign}${Math.round(magnitude * 100)} pts`;
}

/**
 * Two metric sets side by side with an explicit direction of travel.
 *
 * Two independent lists of numbers make the reader do the subtraction — and
 * the subtraction is the entire point of a comparison, whether the arms are
 * defense on/off or before/after a fix.
 */
export function MetricsDeltaTable({
  before,
  after,
  beforeLabel,
  afterLabel,
  withDefinitions = true,
}: {
  before: MetricsResponse | null;
  after: MetricsResponse | null;
  beforeLabel: string;
  afterLabel: string;
  /** Show each metric's definition under its name. Off where the definitions
   * are a step away (Results) and the table is read for the deltas. */
  withDefinitions?: boolean;
}) {
  return (
    <TableWrap>
      <thead>
        <tr>
          <Th className="w-1/2">Metric</Th>
          <Th className="text-right">{beforeLabel}</Th>
          <Th className="text-right">{afterLabel}</Th>
          <Th className="text-right">Change</Th>
        </tr>
      </thead>
      <tbody>
        {METRIC_DESCRIPTORS.map((descriptor) => {
          const rawBefore = before?.[descriptor.key];
          const rawAfter = after?.[descriptor.key];
          const beforeValue = typeof rawBefore === "number" ? rawBefore : null;
          const afterValue = typeof rawAfter === "number" ? rawAfter : null;
          const direction = deltaDirection(descriptor, beforeValue, afterValue);
          return (
            <Tr key={descriptor.key}>
              <Td className="text-fg">
                <span className="block text-xs text-fg">{descriptor.label}</span>
                {withDefinitions && (
                  <span className="block max-w-lg text-2xs text-fg-subtle">
                    {descriptor.definition}
                  </span>
                )}
              </Td>
              <Td className="text-right font-mono text-fg-muted">
                {before ? formatMetric(descriptor, beforeValue) : "—"}
              </Td>
              <Td className="text-right font-mono text-fg">
                {/* State on the dot, value in ink (DESIGN.md › Colors › Ink). */}
                <span className="inline-flex items-center gap-1.5">
                  {afterValue !== null &&
                    metricSeverity(descriptor, afterValue) !== "neutral" && (
                      <SeverityDot severity={metricSeverity(descriptor, afterValue)} />
                    )}
                  {after ? formatMetric(descriptor, afterValue) : "—"}
                </span>
              </Td>
              <Td className="text-right">
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-mono text-2xs",
                    direction === "same" || direction === "unknown" ? "text-fg-subtle" : "text-fg",
                  )}
                >
                  {direction === "better" && <SeverityDot severity="ok" />}
                  {direction === "worse" && <SeverityDot severity="critical" />}
                  {formatDelta(descriptor, beforeValue, afterValue)}
                </span>
              </Td>
            </Tr>
          );
        })}
      </tbody>
    </TableWrap>
  );
}
