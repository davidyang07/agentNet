// Pure control-lifecycle state, mirroring the F3 backend's own transition
// table (docs/M1_F3_PLAN.md §3) client-side for UX responsiveness. The
// backend remains sole authority (BRIEF §6) — this reducer only decides
// what the UI shows and which actions it lets a user attempt; it never
// simulates tick/pause behavior itself (docs/M1_F5_PLAN.md §4/§6).
//
// No React/DOM dependency, so it's unit-testable directly, same discipline
// as lib/stream/reducer.ts.

export type ControlStatus = "idle" | "running" | "paused" | "finished" | "stopped";
export type PendingAction = "start" | "pause" | "resume" | "speed" | "reset" | null;

export type ControlState = {
  experimentId: string | null;
  status: ControlStatus;
  pending: PendingAction;
  speed: number;
  error: string | null;
};

export const initialControlState: ControlState = {
  experimentId: null,
  status: "idle",
  pending: null,
  speed: 1,
  error: null,
};

export function canStart(s: ControlState): boolean {
  return s.status === "idle" && s.pending === null;
}

export function canPause(s: ControlState): boolean {
  return s.status === "running" && s.pending === null;
}

export function canResume(s: ControlState): boolean {
  return s.status === "paused" && s.pending === null;
}

export function canSetSpeed(s: ControlState): boolean {
  return (s.status === "running" || s.status === "paused") && s.pending === null;
}

export function canReset(s: ControlState): boolean {
  return s.experimentId !== null && s.pending === null;
}

export type ControlAction =
  | { type: "start_requested" }
  | { type: "start_succeeded"; experimentId: string; status: ControlStatus }
  | { type: "start_failed"; error: string }
  | { type: "pause_requested" }
  | { type: "pause_succeeded"; status: ControlStatus }
  | { type: "pause_failed"; error: string }
  | { type: "resume_requested" }
  | { type: "resume_succeeded"; status: ControlStatus }
  | { type: "resume_failed"; error: string }
  | { type: "speed_requested" }
  | { type: "speed_succeeded"; speed: number }
  | { type: "speed_failed"; error: string }
  | { type: "reset_requested" }
  | { type: "reset_create_succeeded"; experimentId: string; status: ControlStatus }
  | { type: "reset_stop_succeeded_create_failed"; error: string }
  | { type: "reset_failed"; error: string }
  | { type: "status_synced"; experimentId: string; status: ControlStatus };

export function controlReducer(state: ControlState, action: ControlAction): ControlState {
  switch (action.type) {
    case "start_requested":
      if (!canStart(state)) return state;
      return { ...state, pending: "start", error: null };
    case "start_succeeded":
      return {
        ...state,
        experimentId: action.experimentId,
        status: action.status,
        pending: null,
        error: null,
      };
    case "start_failed":
      return { ...state, pending: null, error: action.error };

    case "pause_requested":
      if (!canPause(state)) return state;
      return { ...state, pending: "pause", error: null };
    case "pause_succeeded":
      return { ...state, status: action.status, pending: null, error: null };
    case "pause_failed":
      return { ...state, pending: null, error: action.error };

    case "resume_requested":
      if (!canResume(state)) return state;
      return { ...state, pending: "resume", error: null };
    case "resume_succeeded":
      return { ...state, status: action.status, pending: null, error: null };
    case "resume_failed":
      return { ...state, pending: null, error: action.error };

    case "speed_requested":
      if (!canSetSpeed(state)) return state;
      return { ...state, pending: "speed", error: null };
    case "speed_succeeded":
      return { ...state, speed: action.speed, pending: null, error: null };
    case "speed_failed":
      return { ...state, pending: null, error: action.error };

    case "reset_requested":
      if (!canReset(state)) return state;
      return { ...state, pending: "reset", error: null };
    case "reset_create_succeeded":
      return {
        ...state,
        experimentId: action.experimentId,
        status: action.status,
        pending: null,
        speed: 1,
        error: null,
      };
    case "reset_stop_succeeded_create_failed":
      return { ...state, status: "stopped", pending: null, error: action.error };
    case "reset_failed":
      return { ...state, pending: null, error: action.error };

    case "status_synced":
      if (action.experimentId !== state.experimentId) return state;
      return { ...state, status: action.status };

    default:
      return state;
  }
}
