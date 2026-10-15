"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { EpidemicResponse } from "@/lib/api/client";
import { selectMetrics, type GraphState } from "@/lib/stream/reducer";

export type OutbreakSample = {
  tick: number;
  healthy: number;
  compromised: number;
  quarantined: number;
  total: number;
};

// One sample per simulated tick; a 2000-tick run is the documented ceiling,
// so the series is bounded without needing a ring buffer.
const MAX_SAMPLES = 2000;

/**
 * Samples the fleet's security-state split once per simulated tick, from the
 * stream the screen is already consuming.
 *
 * A screen opened mid-run (or after it) only sees the ticks streamed while it
 * was open. `history` — the backend's per-tick prevalence, from the epidemic
 * endpoint — fills in the ticks before the first streamed sample, so the
 * curve always starts at tick 0.
 */
export function useOutbreakSeries(
  state: GraphState,
  history?: EpidemicResponse["prevalence"] | null,
): OutbreakSample[] {
  const [series, setSeries] = useState<OutbreakSample[]>([]);
  const lastTick = useRef(-1);
  const experimentId = useRef<string | null>(null);

  useEffect(() => {
    if (state.experimentId !== experimentId.current) {
      experimentId.current = state.experimentId;
      lastTick.current = -1;
      setSeries([]);
      return;
    }
    if (state.nodes.size === 0) return;
    // Ticks can also move backwards, when a replay is scrubbed — rebuild from
    // that point rather than appending an out-of-order sample.
    if (state.tick === lastTick.current) return;
    const metrics = selectMetrics(state);
    const sample: OutbreakSample = {
      tick: state.tick,
      healthy: metrics.healthy,
      compromised: metrics.compromised,
      quarantined: metrics.quarantined,
      total: metrics.total,
    };
    const rewound = state.tick < lastTick.current;
    lastTick.current = state.tick;
    setSeries((prev) => {
      const base = rewound ? prev.filter((s) => s.tick < sample.tick) : prev;
      return [...base, sample].slice(-MAX_SAMPLES);
    });
  }, [state]);

  const total = state.nodes.size;
  return useMemo(() => withHistory(series, history, total), [series, history, total]);
}

/**
 * Prepends the backend's prevalence for every tick before the first streamed
 * sample. Streamed samples always win where both exist: they are what this
 * screen's graph is showing.
 */
export function withHistory(
  series: OutbreakSample[],
  history: EpidemicResponse["prevalence"] | null | undefined,
  total: number,
): OutbreakSample[] {
  if (!history || history.length === 0 || total === 0) return series;
  const firstStreamed = series[0]?.tick ?? Infinity;
  const earlier = history
    .filter((point) => point.tick < firstStreamed)
    .map((point) => ({
      tick: point.tick,
      compromised: point.infectious,
      quarantined: point.quarantined,
      healthy: Math.max(0, total - point.infectious - point.quarantined),
      total,
    }));
  return earlier.length > 0 ? [...earlier, ...series] : series;
}
