"use client";

import { selectMetrics, type GraphState } from "@/lib/stream/reducer";

export function MetricsPanel({ state }: { state: GraphState }) {
  const metrics = selectMetrics(state);

  return (
    <aside className="w-64 shrink-0 overflow-y-auto border-r border-slate-800 p-4 text-sm">
      <h2 className="mb-2 font-medium text-slate-300">Metrics</h2>
      <dl className="space-y-1 text-slate-400">
        <div className="flex justify-between">
          <dt>Total</dt>
          <dd className="font-mono">{metrics.total}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Healthy</dt>
          <dd className="font-mono">{metrics.healthy}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Compromised</dt>
          <dd className="font-mono">{metrics.compromised}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Quarantined</dt>
          <dd className="font-mono">{metrics.quarantined}</dd>
        </div>
        <div className="flex justify-between border-t border-slate-800 pt-1">
          <dt>New compromises</dt>
          <dd className="font-mono">{metrics.newCompromises}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Total exposure</dt>
          <dd className="font-mono">{metrics.totalExposure}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Outbreak duration</dt>
          <dd className="font-mono">{metrics.outbreakDuration}</dd>
        </div>
      </dl>
    </aside>
  );
}
