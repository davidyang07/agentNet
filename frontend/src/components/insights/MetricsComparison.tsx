"use client";

import { useState } from "react";

import {
  ALL_METRIC_DESCRIPTORS,
  EPIDEMIC_METRIC_DESCRIPTORS,
  betterDirection,
  formatMetric,
  metricSeverity,
  type MetricDescriptor,
} from "@/components/insights/SecurityMetrics";
import { SeverityDot } from "@/components/ui/Badge";
import { DisclosureButton } from "@/components/ui/Disclosure";
import { Td, TableWrap, Th, Tr } from "@/components/ui/Table";
import { cn } from "@/lib/cn";
import type { MetricsResponse } from "@/lib/api/client";

// Epidemic metrics are null for a feature a run doesn't use (no immune
// memory, no strains); a row with no value on either side says nothing.
const OPTIONAL_KEYS = new Set(EPIDEMIC_METRIC_DESCRIPTORS.map((d) => d.key));

/** "changed" is a move in a metric where neither direction is better. */
export type DeltaDirection = "better" | "worse" | "changed" | "same" | "unknown";

export function deltaDirection(
  descriptor: MetricDescriptor,
  before: number | null,
  after: number | null,
): DeltaDirection {
  if (before === null || after === null) return "unknown";
  if (before === after) return "same";
  const better = betterDirection(descriptor);
  if (better === null) return "changed";
  return after < before === (better === "lower") ? "better" : "worse";
}

function formatDelta(descriptor: MetricDescriptor, before: number | null, after: number | null) {
  if (before === null || after === null) return "—";
  const diff = after - before;
  if (diff === 0) return "no change";
  const sign = diff > 0 ? "+" : "−";
  const magnitude = Math.abs(diff);
  if (descriptor.kind === "count") return `${sign}${magnitude}`;
  if (descriptor.kind === "latency") return `${sign}${magnitude.toFixed(1)} ticks`;
  if (descriptor.kind === "tick") return `${sign}${magnitude} ticks`;
  if (descriptor.kind === "reproduction") return `${sign}${magnitude.toFixed(2)}`;
  return `${sign}${Math.round(magnitude * 100)} pts`;
}

/**
 * Two metric sets side by side with an explicit direction of travel.
 *
 * Two independent lists of numbers make the reader do the subtraction — and
 * the subtraction is the entire point of a comparison, whether the arms are
 * defense on/off or before/after a fix. Once both arms are in, only the
 * metrics that moved are listed; the unchanged ones are one click away.
 */
export function MetricsDeltaTable({
  before,
  after,
  beforeLabel,
  afterLabel,
  collapseUnchanged = true,
}: {
  before: MetricsResponse | null;
  after: MetricsResponse | null;
  beforeLabel: string;
  afterLabel: string;
  /** Hide metrics whose value is identical in both arms until asked. */
  collapseUnchanged?: boolean;
}) {
  const [showUnchanged, setShowUnchanged] = useState(false);

  const rows = ALL_METRIC_DESCRIPTORS.map((descriptor) => {
    const rawBefore = before?.[descriptor.key];
    const rawAfter = after?.[descriptor.key];
    const beforeValue = typeof rawBefore === "number" ? rawBefore : null;
    const afterValue = typeof rawAfter === "number" ? rawAfter : null;
    return { descriptor, beforeValue, afterValue, changed: beforeValue !== afterValue };
  }).filter(
    (row) =>
      !OPTIONAL_KEYS.has(row.descriptor.key) || row.beforeValue !== null || row.afterValue !== null,
  );
  // Until both arms are in, every row stays so the table's shape is visible.
  const collapsing = collapseUnchanged && before !== null && after !== null;
  const unchanged = rows.filter((row) => !row.changed).length;
  const visible = collapsing && !showUnchanged ? rows.filter((row) => row.changed) : rows;

  return (
    <>
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
          {visible.length === 0 && (
            <Tr>
              <Td className="text-fg-subtle" colSpan={4}>
                No metric changed.
              </Td>
            </Tr>
          )}
          {visible.map(({ descriptor, beforeValue, afterValue }) => {
            const direction = deltaDirection(descriptor, beforeValue, afterValue);
            return (
              <Tr key={descriptor.key}>
                {/* The table is read for the deltas; each definition is on
                    hover, and listed in full on Results. */}
                <Td className="text-xs text-fg" title={descriptor.definition}>
                  {descriptor.label}
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
      {collapsing && unchanged > 0 && (
        <div className="px-3 py-2">
          <DisclosureButton open={showUnchanged} onToggle={() => setShowUnchanged((v) => !v)}>
            {unchanged} unchanged metric{unchanged === 1 ? "" : "s"}
          </DisclosureButton>
        </div>
      )}
    </>
  );
}
