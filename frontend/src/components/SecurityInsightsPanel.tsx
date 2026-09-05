"use client";

import { useEffect, useState } from "react";

import {
  getCriticalNodes,
  getMetrics,
  getProvenance,
  getRemediation,
  getSecurityGraph,
  type CriticalNodeView,
  type MetricsResponse,
  type RemediationResponse,
  type SecurityGraphView,
} from "@/lib/api/client";

// Polls the graph/metrics/remediation endpoints added in docs/PLAN.md §2.5
// -- unlike the event stream, these are computed-on-demand REST resources
// with no push channel, so polling is the same pattern already used for
// the status-completion gap in src/app/page.tsx.
const POLL_INTERVAL_MS = 2000;

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatLatency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)} ticks`;
}

export function formatConfigDiff(diff: Record<string, unknown>): string {
  const entries = Object.entries(diff);
  if (entries.length === 0) return "(no change)";
  return entries.map(([key, value]) => `${key} → ${JSON.stringify(value)}`).join(", ");
}

// The causal-trace ("provenance") viewer's formatting logic -- kept pure and
// unit-tested like this file's other format* helpers, per this codebase's
// established no-jsdom, no-component-rendering-test-setup convention.
export function formatProvenanceChain(chain: string[]): string {
  if (chain.length === 0) return "(no provenance chain)";
  return chain.join(" → ");
}

export type NonAgentNodeTypeSummary = {
  nodeType: string;
  total: number;
  compromised: number;
};

// Deliberately excludes "agent" -- agent counts are already visible via the
// existing stream-derived MetricsPanel and the network graph itself; this
// summary exists to surface the typed non-agent nodes (tools, credentials,
// sentinels, ...) that today have no visual representation anywhere in the
// frontend (docs/PLAN.md §9's "typed-node rendering" gap), without touching
// NetworkGraph.tsx's rendering.
export function summarizeNonAgentNodes(graph: SecurityGraphView): NonAgentNodeTypeSummary[] {
  const counts = new Map<string, { total: number; compromised: number }>();
  for (const node of graph.nodes) {
    if (node.node_type === "agent") continue;
    const entry = counts.get(node.node_type) ?? { total: 0, compromised: 0 };
    entry.total += 1;
    if (node.security_state === "compromised") entry.compromised += 1;
    counts.set(node.node_type, entry);
  }
  return [...counts.entries()]
    .map(([nodeType, { total, compromised }]) => ({ nodeType, total, compromised }))
    .sort((a, b) => a.nodeType.localeCompare(b.nodeType));
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt>{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}

export function SecurityInsightsPanel({ experimentId }: { experimentId: string }) {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [graph, setGraph] = useState<SecurityGraphView | null>(null);
  const [criticalNodes, setCriticalNodes] = useState<CriticalNodeView[]>([]);
  const [remediation, setRemediation] = useState<RemediationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [provenanceNodeId, setProvenanceNodeId] = useState("");
  const [provenanceChain, setProvenanceChain] = useState<string[] | null>(null);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = () => {
      Promise.all([
        getMetrics(experimentId),
        getSecurityGraph(experimentId),
        getCriticalNodes(experimentId, 3),
        getRemediation(experimentId),
      ])
        .then(([metricsResp, graphResp, criticalResp, remediationResp]) => {
          if (cancelled) return;
          setMetrics(metricsResp);
          setGraph(graphResp);
          setCriticalNodes(criticalResp.nodes);
          setRemediation(remediationResp);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
        });
    };
    poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [experimentId]);

  const nonAgentSummary = graph ? summarizeNonAgentNodes(graph) : [];

  const lookupProvenance = () => {
    if (!provenanceNodeId.trim()) return;
    getProvenance(experimentId, provenanceNodeId.trim())
      .then((resp) => {
        setProvenanceChain(resp.chain);
        setProvenanceError(null);
      })
      .catch((err) => {
        setProvenanceChain(null);
        setProvenanceError(err instanceof Error ? err.message : String(err));
      });
  };

  return (
    <aside className="w-72 shrink-0 overflow-y-auto border-l border-slate-800 p-4 text-sm">
      <h2 className="mb-2 font-medium text-slate-300">Security insights</h2>
      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

      {metrics && (
        <dl className="space-y-1 text-slate-400">
          <MetricRow label="Compromise fraction" value={formatPercent(metrics.compromise_fraction)} />
          <MetricRow label="Retained utility" value={formatPercent(metrics.retained_utility)} />
          <MetricRow label="Blast radius" value={formatPercent(metrics.blast_radius_fraction)} />
          <MetricRow label="Privileged exposure" value={String(metrics.privileged_exposure)} />
          <MetricRow
            label="Security-plane integrity"
            value={formatPercent(metrics.security_plane_integrity)}
          />
          <MetricRow label="Attack success rate" value={formatPercent(metrics.attack_success_rate)} />
          <MetricRow
            label="False quarantine rate"
            value={formatPercent(metrics.false_quarantine_rate)}
          />
          <MetricRow label="Detection latency" value={formatLatency(metrics.detection_latency)} />
          <MetricRow
            label="Containment latency"
            value={formatLatency(metrics.containment_latency)}
          />
        </dl>
      )}

      {nonAgentSummary.length > 0 && (
        <>
          <h3 className="mb-1 mt-4 font-medium text-slate-300">Security graph</h3>
          <dl className="space-y-1 text-slate-400">
            {nonAgentSummary.map(({ nodeType, total, compromised }) => (
              <MetricRow
                key={nodeType}
                label={nodeType}
                value={compromised > 0 ? `${compromised}/${total} compromised` : String(total)}
              />
            ))}
          </dl>
        </>
      )}

      {criticalNodes.length > 0 && (
        <>
          <h3 className="mb-1 mt-4 font-medium text-slate-300">Critical nodes</h3>
          <ul className="space-y-1 text-slate-400">
            {criticalNodes.map((node) => (
              <li key={node.id} className="flex justify-between">
                <span className="truncate">{node.id}</span>
                <span className="font-mono">{node.betweenness.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="mb-1 mt-4 font-medium text-slate-300">Causal trace</h3>
      <div className="flex gap-1">
        <input
          type="text"
          value={provenanceNodeId}
          onChange={(e) => setProvenanceNodeId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && lookupProvenance()}
          placeholder="node id"
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-transparent px-2 py-1 text-xs text-slate-300"
        />
        <button
          type="button"
          onClick={lookupProvenance}
          className="rounded-md border border-slate-700 px-2 py-1 text-xs hover:bg-slate-800"
        >
          Trace
        </button>
      </div>
      {provenanceError && <p className="mt-1 text-xs text-red-400">{provenanceError}</p>}
      {provenanceChain !== null && (
        <p className="mt-1 break-words font-mono text-xs text-slate-400">
          {formatProvenanceChain(provenanceChain)}
        </p>
      )}

      <h3 className="mb-1 mt-4 font-medium text-slate-300">Remediation</h3>
      {remediation && remediation.recommendations.length > 0 ? (
        <ul className="space-y-2 text-slate-400">
          {remediation.recommendations.map((rec, i) => (
            <li key={i}>
              <p>{rec.description}</p>
              <p className="font-mono text-xs text-slate-500">
                {formatConfigDiff(rec.config_diff)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-slate-500">No recommendations.</p>
      )}
    </aside>
  );
}
