"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ExperimentConfig, MetricsResponse } from "@/lib/api/client";

import { loadHistoricalArm } from "./loadHistoricalArm";
import { runExperimentToCompletion } from "./runToCompletion";

export type ArmResult = { metrics: MetricsResponse; incomplete?: boolean } | { error: string };

export type ArmState = {
  status: "idle" | "running" | "done" | "error";
  metrics?: MetricsResponse;
  error?: string;
  // Only ever set for a historical arm (compareHistorical) -- a live arm
  // always ran to natural completion, so this is always falsy there.
  incomplete?: boolean;
};

const IDLE_ARM: ArmState = { status: "idle" };

/**
 * Builds the two configs a comparison run pits against each other: identical
 * to `baseConfig` in every field except `defense_enabled` (one arm on, one
 * off). This is the comparison's determinism guarantee — everything else
 * (seed, topology, etc.) is held constant so the only variable is defense.
 */
export function buildComparisonConfigs(
  baseConfig: ExperimentConfig,
): [ExperimentConfig, ExperimentConfig] {
  return [
    { ...baseConfig, defense_enabled: true },
    { ...baseConfig, defense_enabled: false },
  ];
}

/**
 * Runs both comparison arms concurrently and independently — `Promise
 * .allSettled` (rather than `Promise.all`) means arm A's failure never
 * blocks or corrupts arm B's callback, and vice versa. Each arm's outcome is
 * reported exactly once via `onArmUpdate`, as soon as that arm settles,
 * regardless of the other arm's outcome or timing.
 *
 * Aborting `signal` stops both runs on the backend; a cancelled arm reports
 * nothing, since being cancelled is not a failure of the run.
 */
export async function runBothArms(
  baseConfig: ExperimentConfig,
  onArmUpdate: (arm: "A" | "B", result: ArmResult) => void,
  signal?: AbortSignal,
): Promise<void> {
  const [configA, configB] = buildComparisonConfigs(baseConfig);
  const run = (arm: "A" | "B", config: ExperimentConfig) =>
    runExperimentToCompletion(config, { signal, origin: "defense_check" }).then(
      (r) => onArmUpdate(arm, { metrics: r.metrics }),
      (err) => {
        if (signal?.aborted) return;
        onArmUpdate(arm, { error: err instanceof Error ? err.message : String(err) });
      },
    );
  await Promise.allSettled([run("A", configA), run("B", configB)]);
}

/**
 * Runs both arms as loadHistoricalArm calls against two already-persisted
 * experiments, independently (Promise.allSettled) exactly like
 * runBothArms. No backend replay-equivalent -- both arms go through
 * loadReplayData/reduce()/selectMetrics(), the same path replay uses.
 */
export async function runBothHistoricalArms(
  experimentIdA: string,
  experimentIdB: string,
  onArmUpdate: (arm: "A" | "B", result: ArmResult) => void,
): Promise<void> {
  await Promise.allSettled([
    loadHistoricalArm(experimentIdA).then(
      (r) => onArmUpdate("A", { metrics: r.metrics, incomplete: r.incomplete }),
      (err) => onArmUpdate("A", { error: err instanceof Error ? err.message : String(err) }),
    ),
    loadHistoricalArm(experimentIdB).then(
      (r) => onArmUpdate("B", { metrics: r.metrics, incomplete: r.incomplete }),
      (err) => onArmUpdate("B", { error: err instanceof Error ? err.message : String(err) }),
    ),
  ]);
}

/**
 * Thin React wrapper around `runBothArms`/`runBothHistoricalArms`. Owns
 * per-arm status/metrics/error state and guards against overlapping runs:
 * a call while either arm is still `"running"` is ignored rather than
 * starting a second overlapping comparison. A live comparison can be
 * cancelled, and is cancelled when the component using it unmounts, so its
 * runs never outlive the screen that started them.
 */
export function useComparison(): {
  armA: ArmState;
  armB: ArmState;
  runComparison: (baseConfig: ExperimentConfig) => void;
  compareHistorical: (experimentIdA: string, experimentIdB: string) => void;
  cancel: () => void;
} {
  const [armA, setArmA] = useState<ArmState>(IDLE_ARM);
  const [armB, setArmB] = useState<ArmState>(IDLE_ARM);
  // Mirrors whether a comparison is in flight. State alone can't reliably
  // guard re-entrancy here: a comparison call may be issued again before a
  // state update from the previous call has re-rendered, so a ref is used
  // as the synchronous source of truth for the overlap check.
  const runningRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const applyResult = useCallback((arm: "A" | "B", result: ArmResult) => {
    const next: ArmState =
      "error" in result
        ? { status: "error", error: result.error }
        : { status: "done", metrics: result.metrics, incomplete: result.incomplete };
    if (arm === "A") setArmA(next);
    else setArmB(next);
  }, []);

  const runComparison = useCallback(
    (baseConfig: ExperimentConfig) => {
      if (runningRef.current) return;
      runningRef.current = true;
      const controller = new AbortController();
      controllerRef.current = controller;
      setArmA({ status: "running" });
      setArmB({ status: "running" });
      void runBothArms(baseConfig, applyResult, controller.signal).finally(() => {
        // A cancelled comparison already released the guard; don't release
        // it again under a newer one.
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          runningRef.current = false;
        }
      });
    },
    [applyResult],
  );

  const cancel = useCallback(() => {
    if (!controllerRef.current) return;
    controllerRef.current.abort();
    controllerRef.current = null;
    runningRef.current = false;
    setArmA(IDLE_ARM);
    setArmB(IDLE_ARM);
  }, []);

  const compareHistorical = useCallback(
    (experimentIdA: string, experimentIdB: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setArmA({ status: "running" });
      setArmB({ status: "running" });
      void runBothHistoricalArms(experimentIdA, experimentIdB, applyResult).finally(() => {
        runningRef.current = false;
      });
    },
    [applyResult],
  );

  return { armA, armB, runComparison, compareHistorical, cancel };
}
