"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { ConfigForm } from "@/components/ConfigForm";
import { ControlBar } from "@/components/ControlBar";
import { EventStream } from "@/components/EventStream";
import { MetricsPanel } from "@/components/MetricsPanel";
import {
  createExperiment,
  getExperiment,
  pauseExperiment,
  resumeExperiment,
  setSpeed,
  stopExperiment,
  type ExperimentConfig,
} from "@/lib/api/client";
import { canPause, canReset, canResume, canSetSpeed, canStart, controlReducer, initialControlState, type ControlAction } from "@/lib/controls/reducer";
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

// Keyed by experimentId in the parent so a Reset (a brand new experimentId)
// remounts this fresh — GraphState resets for free, no explicit setState
// needed to clear the previous run's nodes/edges/event log.
function ExperimentView({
  experimentId,
  activeConfig,
}: {
  experimentId: string;
  activeConfig: ExperimentConfig;
}) {
  const { state, schemaError } = useExperimentStream(experimentId);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

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
              <dd className="font-mono">{activeConfig.seed}</dd>
            </div>
            <div className="flex justify-between">
              <dt>node_count</dt>
              <dd className="font-mono">{activeConfig.node_count}</dd>
            </div>
            <div className="flex justify-between">
              <dt>edge_density</dt>
              <dd className="font-mono">{activeConfig.edge_density}</dd>
            </div>
            <div className="flex justify-between">
              <dt>p_same</dt>
              <dd className="font-mono">{activeConfig.p_same}</dd>
            </div>
            <div className="flex justify-between">
              <dt>p_cross</dt>
              <dd className="font-mono">{activeConfig.p_cross}</dd>
            </div>
            <div className="flex justify-between border-t border-slate-800 pt-1">
              <dt>tick</dt>
              <dd className="font-mono">{state.tick}</dd>
            </div>
          </dl>
        </aside>

        <MetricsPanel state={state} />

        <section className="flex-1 overflow-hidden">
          <NetworkGraph state={state} onNodeClick={setSelectedAgentId} />
        </section>
      </div>

      {selectedAgentId && <p>Selected: {selectedAgentId}</p>}

      <footer className="h-56 shrink-0 border-t border-slate-800">
        <EventStream events={state.recentEvents} />
      </footer>
    </>
  );
}

export default function Home() {
  const [state, dispatch] = useReducer(controlReducer, initialControlState);
  const stateRef = useRef(state);
  const nextOperationId = useRef(1);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const apply = useCallback((action: ControlAction) => {
    const next = controlReducer(stateRef.current, action);
    if (next === stateRef.current) return false;
    stateRef.current = next;
    dispatch(action);
    return true;
  }, []);

  const handleStart = useCallback((config: ExperimentConfig) => {
    if (!canStart(stateRef.current)) return;
    const operationId = nextOperationId.current++;
    if (!apply({ type: "start_requested", operationId })) return;
    createExperiment(config)
      .then((summary) => {
        apply({
          type: "start_succeeded",
          operationId,
          experimentId: summary.experiment_id,
          status: summary.status,
          config: summary.config,
        });
      })
      .catch((err) => {
        apply({ type: "start_failed", operationId, error: err instanceof Error ? err.message : String(err) });
      });
  }, [apply]);

  const handlePause = useCallback(() => {
    if (!canPause(stateRef.current) || !stateRef.current.experimentId) return;
    const id = stateRef.current.experimentId;
    const operationId = nextOperationId.current++;
    if (!apply({ type: "pause_requested", operationId })) return;
    pauseExperiment(id)
      .then((summary) => apply({ type: "pause_succeeded", operationId, status: summary.status }))
      .catch((err) => {
        apply({ type: "pause_failed", operationId, error: err instanceof Error ? err.message : String(err) });
      });
  }, [apply]);

  const handleResume = useCallback(() => {
    if (!canResume(stateRef.current) || !stateRef.current.experimentId) return;
    const id = stateRef.current.experimentId;
    const operationId = nextOperationId.current++;
    if (!apply({ type: "resume_requested", operationId })) return;
    resumeExperiment(id)
      .then((summary) => apply({ type: "resume_succeeded", operationId, status: summary.status }))
      .catch((err) => {
        apply({ type: "resume_failed", operationId, error: err instanceof Error ? err.message : String(err) });
      });
  }, [apply]);

  const handleSpeedChange = useCallback(
    (multiplier: number) => {
      if (!canSetSpeed(stateRef.current) || !stateRef.current.experimentId) return;
      const id = stateRef.current.experimentId;
      const operationId = nextOperationId.current++;
      if (!apply({ type: "speed_requested", operationId })) return;
      setSpeed(id, multiplier)
        .then(() => apply({ type: "speed_succeeded", operationId, speed: multiplier }))
        .catch((err) => {
          apply({ type: "speed_failed", operationId, error: err instanceof Error ? err.message : String(err) });
        });
    },
    [apply],
  );

  // Reset ordering (docs/M1_F5_PLAN.md §5): await stopping the old
  // experiment (idempotent / 404-tolerant — either way it's gone), only
  // then create the new one, and only then swap the active experimentId/
  // status — so there is never a moment with two experiments simultaneously
  // active in local state, and a create failure after a successful stop is
  // reported as "stopped", not silently left pointing at a dead run.
  const handleReset = useCallback(async () => {
    if (!canReset(stateRef.current) || !stateRef.current.experimentId) return;
    const oldId = stateRef.current.experimentId;
    const configToRerun = stateRef.current.activeConfig;
    if (!configToRerun) return;
    const operationId = nextOperationId.current++;
    if (!apply({ type: "reset_requested", operationId })) return;

    try {
      await stopExperiment(oldId);
    } catch (err) {
      // A 404 means the old experiment is already gone (evicted) — that's
      // the desired end state, not a failure, so fall through to create.
      // Anything else means the old run's stop status is unknown: abort
      // without touching state, so it's cleanly retryable.
      if (!(err instanceof Error && err.message.includes("404"))) {
        apply({ type: "reset_failed", operationId, error: err instanceof Error ? err.message : String(err) });
        return;
      }
    }

    // The old run is now confirmed stopped-or-gone. A failure from here on
    // must not leave local state claiming the old run is still "running".
    try {
      const summary = await createExperiment(configToRerun);
      apply({
        type: "reset_create_succeeded",
        operationId,
        experimentId: summary.experiment_id,
        status: summary.status,
        config: summary.config,
      });
    } catch (err) {
      apply({
        type: "reset_stop_succeeded_create_failed",
        operationId,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }, [apply]);

  // Closes the REST/WS status gap for natural completion (docs/M1_F5_PLAN.md §4).
  useEffect(() => {
    if (state.status !== "running" || state.pending !== null || !state.experimentId) return;
    const id = state.experimentId;
    const revision = state.revision;
    const controller = new AbortController();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      getExperiment(id, controller.signal)
        .then((summary) => apply({ type: "status_synced", experimentId: id, revision, status: summary.status }))
        .catch(() => {
          // Transient network hiccup — next tick retries. A genuine 404
          // (evicted out from under us) is left for the user's next
          // control action to surface, rather than guessing here.
        })
        .finally(() => {
          if (!cancelled) timer = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
        });
    };
    timer = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [apply, state.status, state.pending, state.experimentId, state.revision]);

  return (
    <main className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 flex-col gap-3 border-b border-slate-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">AgentNet</h1>
          <ControlBar
            state={state}
            onPause={handlePause}
            onResume={handleResume}
            onReset={handleReset}
            onSpeedChange={handleSpeedChange}
          />
        </div>
        <ConfigForm disabled={!canStart(state)} onStart={handleStart} />
      </header>

      {state.experimentId && (
        <ExperimentView
          key={state.experimentId}
          experimentId={state.experimentId}
          activeConfig={state.activeConfig!}
        />
      )}
    </main>
  );
}
