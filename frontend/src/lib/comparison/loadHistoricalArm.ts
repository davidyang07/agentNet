import { foldEvents, loadReplayData } from "@/lib/replay/loadReplayData";
import { selectMetrics } from "@/lib/stream/reducer";

export type HistoricalArmResult = {
  experimentId: string;
  metrics: ReturnType<typeof selectMetrics>;
  incomplete: boolean;
};

/**
 * Direct sibling of runToCompletion.ts for a *historical* arm: reuses
 * loadReplayData's snapshot+pagination fetch (the same path replay uses)
 * and folds every returned event through reduce() to compute final
 * metrics via the exact same selectMetrics() live comparison uses -- no
 * backend reduce-equivalent, no second fold implementation
 * (docs/PHASE_1_5_PLAN.md §10).
 */
export async function loadHistoricalArm(experimentId: string): Promise<HistoricalArmResult> {
  const data = await loadReplayData(experimentId);
  const finalState = foldEvents(data.initialState, data.events, data.events.length);
  return { experimentId, metrics: selectMetrics(finalState), incomplete: data.incomplete };
}
