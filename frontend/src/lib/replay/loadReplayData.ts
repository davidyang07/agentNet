import { fetchEventHistory, fetchReplaySnapshot, getExperimentDetail } from "@/lib/api/client";
import {
  type Event,
  type GraphState,
  type StreamFrame,
  initialGraphState,
  reduce,
} from "@/lib/stream/reducer";

const EVENT_PAGE_LIMIT = 500;

export type ReplayData = {
  // Conservative: true unless the experiment's persisted record proved a
  // gapless seq range at finalize time. A crashed/never-finalized run
  // (is_complete still null) is exactly as untrustworthy for replay as a
  // detected gap (is_complete === false).
  incomplete: boolean;
  initialState: GraphState;
  events: Event[];
};

/**
 * Headless (non-React) helper, the direct sibling of
 * lib/comparison/runToCompletion.ts: fetches a regenerated tick-0 snapshot
 * plus the full persisted event log after it, once, and folds the snapshot
 * through the same pure reduce() the live view uses. The returned `events`
 * array never includes an initial (pre-first-tick) event -- pagination starts
 * at `snapshot.last_seq` (the last of the EXPERIMENT_STARTED/AGENT_CREATED/
 * seed-compromise events the regenerated snapshot already reflects), so the
 * seeded patient-zero compromise is never re-delivered through the event
 * branch, while the first tick's own events (also stamped sim_tick 0) are.
 */
export async function loadReplayData(
  experimentId: string,
  onProgress?: (loaded: number) => void,
): Promise<ReplayData> {
  const detail = await getExperimentDetail(experimentId);
  const snapshot = await fetchReplaySnapshot(experimentId);
  const initialState = reduce(initialGraphState, snapshot as StreamFrame);

  const events: Event[] = [];
  let sinceSeq = snapshot.last_seq;
  for (;;) {
    const page = await fetchEventHistory(experimentId, sinceSeq, EVENT_PAGE_LIMIT);
    events.push(...page.events);
    onProgress?.(events.length);
    if (page.next_seq === null) break;
    sinceSeq = page.next_seq;
  }

  return { incomplete: detail.is_complete !== true, initialState, events };
}

/** Cheap at this project's data volumes: folds `count` events from `events`
 * onto `from` fresh via reduce(), rather than maintaining incremental undo
 * state -- shared by both seek and (indirectly) interval-driven playback. */
export function foldEvents(from: GraphState, events: Event[], count: number): GraphState {
  let state = from;
  for (let i = 0; i < count; i++) {
    state = reduce(state, { type: "event", event: events[i] });
  }
  return state;
}
