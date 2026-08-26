"use client";

import { useCallback, useRef, useState } from "react";

import type { ExperimentConfig } from "@/lib/api/client";
import type { selectMetrics } from "@/lib/stream/reducer";

import { runExperimentToCompletion } from "./runToCompletion";

export type ArmResult = { metrics: ReturnType<typeof selectMetrics> } | { error: string };

export type ArmState = {
  status: "idle" | "running" | "done" | "error";
  metrics?: ReturnType<typeof selectMetrics>;
  error?: string;
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
 */
export async function runBothArms(
  baseConfig: ExperimentConfig,
  onArmUpdate: (arm: "A" | "B", result: ArmResult) => void,
): Promise<void> {
  const [configA, configB] = buildComparisonConfigs(baseConfig);
  await Promise.allSettled([
    runExperimentToCompletion(configA).then(
      (r) => onArmUpdate("A", { metrics: r.metrics }),
      (err) => onArmUpdate("A", { error: err instanceof Error ? err.message : String(err) }),
    ),
    runExperimentToCompletion(configB).then(
      (r) => onArmUpdate("B", { metrics: r.metrics }),
      (err) => onArmUpdate("B", { error: err instanceof Error ? err.message : String(err) }),
    ),
  ]);
}

/**
 * Thin React wrapper around `runBothArms`. Owns per-arm status/metrics/error
 * state and guards against overlapping runs: a `runComparison` call while
 * either arm is still `"running"` is ignored rather than starting a second
 * overlapping comparison.
 */
export function useComparison(): {
  armA: ArmState;
  armB: ArmState;
  runComparison: (baseConfig: ExperimentConfig) => void;
} {
  const [armA, setArmA] = useState<ArmState>(IDLE_ARM);
  const [armB, setArmB] = useState<ArmState>(IDLE_ARM);
  // Mirrors whether a comparison is in flight. State alone can't reliably
  // guard re-entrancy here: `runComparison` may be called again before a
  // state update from the previous call has re-rendered, so a ref is used
  // as the synchronous source of truth for the overlap check.
  const runningRef = useRef(false);

  const runComparison = useCallback((baseConfig: ExperimentConfig) => {
    if (runningRef.current) return;
    runningRef.current = true;

    setArmA({ status: "running" });
    setArmB({ status: "running" });

    const onArmUpdate = (arm: "A" | "B", result: ArmResult) => {
      const next: ArmState =
        "error" in result
          ? { status: "error", error: result.error }
          : { status: "done", metrics: result.metrics };
      if (arm === "A") setArmA(next);
      else setArmB(next);
    };

    void runBothArms(baseConfig, onArmUpdate).finally(() => {
      runningRef.current = false;
    });
  }, []);

  return { armA, armB, runComparison };
}
