"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { EventStream } from "@/components/EventStream";
import { createExperiment, type ExperimentConfig } from "@/lib/api/client";
import { useExperimentStream } from "@/lib/stream/useExperimentStream";

// Sigma touches WebGL2RenderingContext at module load — it can only ever
// run in the browser, so it must be excluded from server-side rendering.
const NetworkGraph = dynamic(
  () => import("@/components/NetworkGraph").then((mod) => mod.NetworkGraph),
  { ssr: false },
);

// SPEC §6.2's own canonical demo config.
const CANONICAL_CONFIG: ExperimentConfig = {
  seed: 42,
  node_count: 60,
  edge_density: 2,
  software_type_count: 3,
  p_same: 0.15,
  p_cross: 0.03,
  max_ticks: 200,
  detector_sensitivity: 0.2,
  defense_enabled: true,
  initial_compromised: "highest_degree",
};

// Keyed by experimentId in the parent so a Reset (a brand new experimentId)
// remounts this fresh — GraphState resets for free, no explicit setState
// needed to clear the previous run's nodes/edges/event log.
function ExperimentView({ experimentId }: { experimentId: string }) {
  const { state, schemaError } = useExperimentStream(experimentId);

  return (
    <>
      {schemaError && (
        <div className="shrink-0 border-b border-red-900 bg-red-950 px-4 py-2 text-sm text-red-300">
          {schemaError}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-slate-800 p-4 text-sm">
          <h2 className="mb-2 font-medium text-slate-300">Experiment</h2>
          <dl className="space-y-1 text-slate-400">
            <div className="flex justify-between">
              <dt>seed</dt>
              <dd className="font-mono">{CANONICAL_CONFIG.seed}</dd>
            </div>
            <div className="flex justify-between">
              <dt>node_count</dt>
              <dd className="font-mono">{CANONICAL_CONFIG.node_count}</dd>
            </div>
            <div className="flex justify-between">
              <dt>edge_density</dt>
              <dd className="font-mono">{CANONICAL_CONFIG.edge_density}</dd>
            </div>
            <div className="flex justify-between">
              <dt>p_same</dt>
              <dd className="font-mono">{CANONICAL_CONFIG.p_same}</dd>
            </div>
            <div className="flex justify-between">
              <dt>p_cross</dt>
              <dd className="font-mono">{CANONICAL_CONFIG.p_cross}</dd>
            </div>
            <div className="flex justify-between border-t border-slate-800 pt-1">
              <dt>tick</dt>
              <dd className="font-mono">{state.tick}</dd>
            </div>
          </dl>
        </aside>

        <section className="flex-1 overflow-hidden">
          <NetworkGraph state={state} />
        </section>
      </div>

      <footer className="h-56 shrink-0 border-t border-slate-800">
        <EventStream events={state.recentEvents} />
      </footer>
    </>
  );
}

export default function Home() {
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // No "Start" control (BRIEF §4) — the canonical run begins on mount.
  // Reset re-issues this same call with the same seed.
  const start = useCallback(() => {
    createExperiment(CANONICAL_CONFIG)
      .then((summary) => {
        setError(null);
        setExperimentId(summary.experiment_id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    start();
  }, [start]);

  return (
    <main className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
        <h1 className="text-lg font-semibold">AgentNet</h1>
        <button
          onClick={start}
          className="rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800"
        >
          Reset
        </button>
      </header>

      {error && (
        <div className="shrink-0 border-b border-red-900 bg-red-950 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {experimentId && <ExperimentView key={experimentId} experimentId={experimentId} />}
    </main>
  );
}
