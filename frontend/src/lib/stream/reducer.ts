import type { components } from "@/lib/api/schema.d.ts";

export type NodeView = components["schemas"]["NodeView"];
export type EdgeView = components["schemas"]["EdgeView"];
export type Event = components["schemas"]["Event"];
export type SnapshotFrame = components["schemas"]["SnapshotFrame"];
export type EventFrame = components["schemas"]["EventFrame"];
export type StreamFrame = SnapshotFrame | EventFrame;

export const CURRENT_SCHEMA_VERSION = 1;
export const EVENT_LOG_CAP = 200;

export type GraphState = {
  experimentId: string | null;
  lastSeq: number;
  tick: number;
  nodes: Map<string, NodeView>;
  edges: EdgeView[];
  recentEvents: Event[]; // capped at 200 for the bottom panel
};

export const initialGraphState: GraphState = {
  experimentId: null,
  lastSeq: -1,
  tick: 0,
  nodes: new Map(),
  edges: [],
  recentEvents: [],
};

/**
 * Pure — no React/DOM dependency, so Phase 1.5 replay can drive it from a
 * stored log with zero changes. Throws on an unrecognized schema_version;
 * the caller is responsible for surfacing that as a hard UI error rather
 * than silently skipping the frame.
 */
export function reduce(state: GraphState, frame: StreamFrame): GraphState {
  if (frame.type === "snapshot") {
    const nodes = new Map<string, NodeView>();
    for (const node of frame.nodes) {
      nodes.set(node.id, node);
    }
    return {
      experimentId: frame.experiment_id,
      lastSeq: frame.last_seq,
      tick: frame.sim_tick,
      nodes,
      edges: frame.edges,
      recentEvents: state.recentEvents,
    };
  }

  const event = frame.event;
  if (event.schema_version !== CURRENT_SCHEMA_VERSION) {
    throw new Error(
      `Unrecognized schema_version ${event.schema_version}; this client understands ${CURRENT_SCHEMA_VERSION}.`,
    );
  }

  const recentEvents = [...state.recentEvents, event].slice(-EVENT_LOG_CAP);
  let nodes = state.nodes;

  if (event.event_type === "COMPROMISE_SUCCEEDED" && event.target_agent_id) {
    const existing = state.nodes.get(event.target_agent_id);
    if (existing) {
      nodes = new Map(state.nodes);
      nodes.set(event.target_agent_id, { ...existing, security_state: "compromised" });
    }
  }

  return {
    ...state,
    lastSeq: event.seq,
    tick: event.sim_tick,
    nodes,
    recentEvents,
  };
}
