import { MetricTile, StatList, StatRow } from "@/components/ui/Metric";
import { formatLatency, formatPercent } from "@/lib/format";
import type { MetricsResponse } from "@/lib/api/client";
import {
  severityForHealth,
  severityForReproduction,
  severityForRisk,
  type Severity,
} from "@/lib/severity";

export type MetricDescriptor = {
  key: keyof MetricsResponse;
  label: string;
  definition: string;
  kind: "risk" | "health" | "count" | "latency" | "reproduction" | "tick";
  /** Which way is an improvement, when that isn't the kind's usual one;
   * null when neither is (when an outbreak peaks is not better or worse). */
  better?: "lower" | "higher" | null;
  /** Severity, when the kind's usual rule would mislead. */
  severity?: (value: number) => Severity;
};

/**
 * Every metric the backend computes, with the definition it is computed from.
 * A security number without its definition is not a claim anyone can check —
 * and the definitions here are literally `app/metrics/compute.py`'s.
 */
export const METRIC_DESCRIPTORS: readonly MetricDescriptor[] = [
  {
    key: "compromise_fraction",
    label: "Compromise fraction",
    definition: "Compromised agents ÷ all agents.",
    kind: "risk",
  },
  {
    key: "blast_radius_fraction",
    label: "Blast radius",
    definition:
      "Agents reachable from any currently-compromised node across propagation-capable edges, never through a quarantined agent ÷ all agents.",
    kind: "risk",
  },
  {
    key: "attack_success_rate",
    label: "Attack success rate",
    definition:
      "New compromises ÷ attack attempts. The seeded compromise and a second win on an already-won target don't count; model-gateway failures are counted separately.",
    kind: "risk",
  },
  {
    key: "false_quarantine_rate",
    label: "False-quarantine rate",
    definition:
      "Quarantines exercised without a preceding detection ÷ all quarantines — the cost of a subverted quarantine authority.",
    kind: "risk",
  },
  {
    key: "retained_utility",
    label: "Retained utility",
    definition: "Agents neither compromised nor quarantined ÷ all agents.",
    kind: "health",
  },
  {
    key: "security_plane_integrity",
    label: "Security-plane integrity",
    definition: "Healthy sentinels and security controls ÷ all of them.",
    kind: "health",
  },
  {
    key: "privileged_exposure",
    label: "Privileged exposure",
    definition: "Credential and resource nodes inside the blast radius.",
    kind: "count",
  },
  {
    key: "detection_latency",
    label: "Detection latency",
    definition: "Mean ticks from a node's compromise to the first anomaly detected on it.",
    kind: "latency",
  },
  {
    key: "containment_latency",
    label: "Containment latency",
    definition:
      "Mean ticks from detection to the first legitimate quarantine. Not reported while detection and quarantine happen in the same tick, the only response mode today.",
    kind: "latency",
  },
  {
    key: "gateway_failure_count",
    label: "Model-gateway failures",
    definition:
      "Real-agent attacks that never reached the model (request budget exhausted or every retry failed) — not counted as defended.",
    kind: "count",
  },
];

/**
 * The epidemic view of the same run (docs/PLAN.md §6, §14.4 C.1–C.4), read
 * from the infection tree. The immune-memory and strain metrics are null
 * unless those features are on, and are then left out of lists.
 */
export const EPIDEMIC_METRIC_DESCRIPTORS: readonly MetricDescriptor[] = [
  {
    key: "r0_estimate",
    label: "R0 estimate",
    definition:
      "Mean offspring of generations 0 and 1 of the infection tree: how many agents each early infection went on to infect. Below 1, the outbreak dies out.",
    kind: "reproduction",
  },
  {
    key: "final_size",
    label: "Final size",
    definition: "Agents ever infected ÷ all agents.",
    kind: "risk",
  },
  {
    key: "peak_prevalence",
    label: "Peak prevalence",
    definition: "The largest fraction of agents compromised at the end of a tick.",
    kind: "risk",
  },
  {
    key: "peak_tick",
    label: "Peak tick",
    definition: "The first tick at which prevalence reached its peak.",
    kind: "tick",
    better: null,
  },
  {
    key: "serial_interval",
    label: "Serial interval",
    definition: "Mean ticks from a source's infection to its target's.",
    kind: "latency",
    better: null,
  },
  {
    key: "strains_observed",
    label: "Strains observed",
    definition: "Distinct worm strains among infected agents. Tracked when strains mutate.",
    kind: "count",
    // One strain is an outbreak that never mutated; only variants matter.
    severity: (value) => (value > 1 ? "warn" : "neutral"),
  },
  {
    key: "immunity_coverage",
    label: "Immunity coverage",
    definition: "Agents holding a legitimate threat signature ÷ all agents.",
    kind: "health",
  },
  {
    key: "signature_block_rate",
    label: "Signature block rate",
    definition: "Attacks blocked by a held signature ÷ attack attempts.",
    kind: "health",
  },
  {
    key: "benign_block_rate",
    label: "Benign block rate",
    definition:
      "Benign traffic blocked ÷ benign traffic screened — the autoimmune cost of immune memory.",
    kind: "risk",
  },
];

export const ALL_METRIC_DESCRIPTORS: readonly MetricDescriptor[] = [
  ...METRIC_DESCRIPTORS,
  ...EPIDEMIC_METRIC_DESCRIPTORS,
];

/** Which way is an improvement for this metric, if either. */
export function betterDirection(descriptor: MetricDescriptor): "lower" | "higher" | null {
  if (descriptor.better !== undefined) return descriptor.better;
  return descriptor.kind === "health" ? "higher" : "lower";
}

export function metricSeverity(descriptor: MetricDescriptor, value: number | null): Severity {
  if (value === null) return "neutral";
  if (descriptor.severity) return descriptor.severity(value);
  if (descriptor.kind === "risk") return severityForRisk(value);
  if (descriptor.kind === "health") return severityForHealth(value);
  if (descriptor.kind === "reproduction") return severityForReproduction(value);
  if (descriptor.kind === "count") return value > 0 ? "high" : "ok";
  return "neutral";
}

export function formatMetric(descriptor: MetricDescriptor, value: number | null): string {
  if (value === null) return "—";
  if (descriptor.kind === "latency") return formatLatency(value);
  if (descriptor.kind === "count") return String(value);
  if (descriptor.kind === "reproduction") return value.toFixed(2);
  if (descriptor.kind === "tick") return `t${value}`;
  return formatPercent(value);
}

/** The four numbers that answer "how bad is it" first, shown as tiles. */
export const HEADLINE_METRIC_KEYS: ReadonlyArray<keyof MetricsResponse> = [
  "compromise_fraction",
  "blast_radius_fraction",
  "retained_utility",
  "security_plane_integrity",
];

/** Every metric that is not a headline tile, in descriptor order. */
export const SECONDARY_METRIC_KEYS: ReadonlyArray<keyof MetricsResponse> = METRIC_DESCRIPTORS.map(
  (d) => d.key,
).filter((key) => !HEADLINE_METRIC_KEYS.includes(key));

export function PostureTiles({ metrics }: { metrics: MetricsResponse }) {
  const tiles = HEADLINE_METRIC_KEYS.map(
    (key) => METRIC_DESCRIPTORS.find((d) => d.key === key) as MetricDescriptor,
  );

  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {tiles.map((descriptor) => {
        const raw = metrics[descriptor.key];
        const value = typeof raw === "number" ? raw : null;
        const severity = metricSeverity(descriptor, value);
        return (
          <MetricTile
            key={descriptor.key}
            label={descriptor.label}
            hint={descriptor.definition}
            value={formatMetric(descriptor, value)}
            severity={severity}
            fraction={value ?? 0}
          />
        );
      })}
    </div>
  );
}

/** Full metric list with definitions, for the Metrics screen and side panels. */
export function MetricsList({
  metrics,
  keys,
  withDefinitions,
  skipMissing,
}: {
  metrics: MetricsResponse;
  keys?: ReadonlyArray<keyof MetricsResponse>;
  withDefinitions?: boolean;
  /** Leave out metrics the run has no value for (a feature that is off). */
  skipMissing?: boolean;
}) {
  const descriptors = (keys
    ? ALL_METRIC_DESCRIPTORS.filter((d) => keys.includes(d.key))
    : METRIC_DESCRIPTORS
  ).filter((d) => !skipMissing || typeof metrics[d.key] === "number");

  return (
    <StatList>
      {descriptors.map((descriptor) => {
        const raw = metrics[descriptor.key];
        const value = typeof raw === "number" ? raw : null;
        return (
          <StatRow
            key={descriptor.key}
            label={
              withDefinitions ? (
                <span className="block">
                  <span className="block text-xs text-fg-muted">{descriptor.label}</span>
                  <span className="block max-w-md text-2xs text-fg-subtle">
                    {descriptor.definition}
                  </span>
                </span>
              ) : (
                descriptor.label
              )
            }
            hint={withDefinitions ? undefined : descriptor.definition}
            value={formatMetric(descriptor, value)}
            severity={metricSeverity(descriptor, value)}
          />
        );
      })}
    </StatList>
  );
}
