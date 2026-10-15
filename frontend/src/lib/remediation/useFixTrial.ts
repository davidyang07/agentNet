"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ExperimentConfig, MetricsResponse } from "@/lib/api/client";
import { runExperimentToCompletion } from "@/lib/comparison/runToCompletion";

export type TrialArm =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; metrics: MetricsResponse; experimentId: string }
  | { status: "error"; error: string };

export type FixTrial = {
  /** The recommendation being validated, keyed by its config diff. */
  diffKey: string | null;
  before: TrialArm;
  after: TrialArm;
  running: boolean;
  /** Runs the baseline config and the remediated config to completion. */
  validate: (baseConfig: ExperimentConfig, configDiff: Record<string, unknown>) => void;
  /** Stops both runs on the backend and clears the trial. */
  cancel: () => void;
};

const IDLE: TrialArm = { status: "idle" };

/**
 * The "re-test" half of Remediate → Re-test.
 *
 * A recommendation's `config_diff` is directly usable as a `POST /api/experiments`
 * body, so validating a fix needs no new machinery: run the baseline config and
 * the patched config to completion and compare the same metrics. Previously the
 * UI displayed the diff and left the operator to reproduce it by hand.
 *
 * Both runs are recorded as `fix_trial` runs, so history can tell them from
 * the operator's own assessments. They are stopped if the trial is cancelled
 * or the component using it unmounts.
 */
export function useFixTrial(): FixTrial {
  const [diffKey, setDiffKey] = useState<string | null>(null);
  const [before, setBefore] = useState<TrialArm>(IDLE);
  const [after, setAfter] = useState<TrialArm>(IDLE);
  // A ref, not state: a second click can arrive before the state update that
  // would have blocked it has re-rendered.
  const runningRef = useRef(false);
  const [running, setRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const validate = useCallback(
    (baseConfig: ExperimentConfig, configDiff: Record<string, unknown>) => {
      if (runningRef.current) return;
      runningRef.current = true;
      const controller = new AbortController();
      controllerRef.current = controller;
      const { signal } = controller;
      setRunning(true);
      setDiffKey(JSON.stringify(configDiff));
      setBefore({ status: "running" });
      setAfter({ status: "running" });

      const remediated = { ...baseConfig, ...configDiff } as ExperimentConfig;
      const run = (config: ExperimentConfig, setArm: (arm: TrialArm) => void) =>
        runExperimentToCompletion(config, { signal, origin: "fix_trial" }).then(
          (result) =>
            setArm({ status: "done", metrics: result.metrics, experimentId: result.experimentId }),
          (err) => {
            // Cancelled, not failed: cancel() has already reset the trial.
            if (signal.aborted) return;
            setArm({ status: "error", error: err instanceof Error ? err.message : String(err) });
          },
        );

      // allSettled, not all: one arm failing must not hide the other's result.
      void Promise.allSettled([run(baseConfig, setBefore), run(remediated, setAfter)]).finally(
        () => {
          if (controllerRef.current !== controller) return;
          controllerRef.current = null;
          runningRef.current = false;
          setRunning(false);
        },
      );
    },
    [],
  );

  const cancel = useCallback(() => {
    if (!controllerRef.current) return;
    controllerRef.current.abort();
    controllerRef.current = null;
    runningRef.current = false;
    setRunning(false);
    setDiffKey(null);
    setBefore(IDLE);
    setAfter(IDLE);
  }, []);

  return { diffKey, before, after, running, validate, cancel };
}
