"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useReducer } from "react";

import { ControlBar } from "@/components/ControlBar";
import { EventStream } from "@/components/EventStream";
import {
  createExperiment,
  getExperiment,
  pauseExperiment,
  resumeExperiment,
  setSpeed,
  stopExperiment,
  type ExperimentConfig,
} from "@/lib/api/client";
import { controlReducer, initialControlState } from "@/lib/controls/reducer";
import { useExperimentStream } from "@/lib/stream/useExperimentStream";

// While a run is "running", the WS stream never surfaces a status change on
// its own (SnapshotFrame.status is sent only once, on connect/reconnect;
// EventFrame carries no status field) — so natural completion (reaching
// max_ticks, or full containment) is otherwise invisible to a connected
// client. Poll GET /{id} to close that gap (docs/M1_F5_PLAN.md §4).
const STATUS_POLL_INTERVAL_MS = 1000;

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
  const [state, dispatch] = useReducer(controlReducer, initialControlState);

  const handleStart = useCallback(() => {
    dispatch({ type: "start_requested" });
    createExperiment(CANONICAL_CONFIG)
      .then((summary) => {
        dispatch({
          type: "start_succeeded",
          experimentId: summary.experiment_id,
          status: summary.status,
        });
      })
      .catch((err) => {
        dispatch({ type: "start_failed", error: err instanceof Error ? err.message : String(err) });
      });
  }, []);

  const handlePause = useCallback(() => {
    if (!state.experimentId) return;
    dispatch({ type: "pause_requested" });
    pauseExperiment(state.experimentId)
      .then((summary) => dispatch({ type: "pause_succeeded", status: summary.status }))
      .catch((err) => {
        dispatch({ type: "pause_failed", error: err instanceof Error ? err.message : String(err) });
      });
  }, [state.experimentId]);

  const handleResume = useCallback(() => {
    if (!state.experimentId) return;
    dispatch({ type: "resume_requested" });
    resumeExperiment(state.experimentId)
      .then((summary) => dispatch({ type: "resume_succeeded", status: summary.status }))
      .catch((err) => {
        dispatch({ type: "resume_failed", error: err instanceof Error ? err.message : String(err) });
      });
  }, [state.experimentId]);

  const handleSpeedChange = useCallback(
    (multiplier: number) => {
      if (!state.experimentId) return;
      dispatch({ type: "speed_requested" });
      setSpeed(state.experimentId, multiplier)
        .then(() => dispatch({ type: "speed_succeeded", speed: multiplier }))
        .catch((err) => {
          dispatch({ type: "speed_failed", error: err instanceof Error ? err.message : String(err) });
        });
    },
    [state.experimentId],
  );

  // Reset ordering (docs/M1_F5_PLAN.md §5): await stopping the old
  // experiment (idempotent / 404-tolerant — either way it's gone), only
  // then create the new one, and only then swap the active experimentId/
  // status — so there is never a moment with two experiments simultaneously
  // active in local state, and a create failure after a successful stop is
  // reported as "stopped", not silently left pointing at a dead run.
  const handleReset = useCallback(async () => {
    if (!state.experimentId) return;
    const oldId = state.experimentId;
    dispatch({ type: "reset_requested" });

    try {
      await stopExperiment(oldId);
    } catch (err) {
      // A 404 means the old experiment is already gone (evicted) — that's
      // the desired end state, not a failure, so fall through to create.
      // Anything else means the old run's stop status is unknown: abort
      // without touching state, so it's cleanly retryable.
      if (!(err instanceof Error && err.message.includes("404"))) {
        dispatch({ type: "reset_failed", error: err instanceof Error ? err.message : String(err) });
        return;
      }
    }

    // The old run is now confirmed stopped-or-gone. A failure from here on
    // must not leave local state claiming the old run is still "running".
    try {
      const summary = await createExperiment(CANONICAL_CONFIG);
      dispatch({
        type: "reset_create_succeeded",
        experimentId: summary.experiment_id,
        status: summary.status,
      });
    } catch (err) {
      dispatch({
        type: "reset_stop_succeeded_create_failed",
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }, [state.experimentId]);

  // Closes the REST/WS status gap for natural completion (docs/M1_F5_PLAN.md §4).
  useEffect(() => {
    if (state.status !== "running" || !state.experimentId) return;
    const id = state.experimentId;
    const interval = setInterval(() => {
      getExperiment(id)
        .then((summary) => dispatch({ type: "status_synced", experimentId: id, status: summary.status }))
        .catch(() => {
          // Transient network hiccup — next tick retries. A genuine 404
          // (evicted out from under us) is left for the user's next
          // control action to surface, rather than guessing here.
        });
    }, STATUS_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [state.status, state.experimentId]);

  return (
    <main className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
        <h1 className="text-lg font-semibold">AgentNet</h1>
        <ControlBar
          state={state}
          onStart={handleStart}
          onPause={handlePause}
          onResume={handleResume}
          onReset={handleReset}
          onSpeedChange={handleSpeedChange}
        />
      </header>

      {state.experimentId && (
        <ExperimentView key={state.experimentId} experimentId={state.experimentId} />
      )}
    </main>
  );
}
