import {
  canPause,
  canReset,
  canResume,
  canSetSpeed,
  canStart,
  type ControlState,
} from "@/lib/controls/reducer";

const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 4, 8];

const BUTTON_CLASS =
  "rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

export function ControlBar({
  state,
  onStart,
  onPause,
  onResume,
  onReset,
  onSpeedChange,
}: {
  state: ControlState;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onSpeedChange: (multiplier: number) => void;
}) {
  const paused = state.status === "paused";

  return (
    <div className="flex items-center gap-2">
      <span className="mr-1 rounded border border-slate-700 px-2 py-0.5 font-mono text-xs uppercase text-slate-400">
        {state.status}
      </span>

      <button className={BUTTON_CLASS} onClick={onStart} disabled={!canStart(state)}>
        Start
      </button>

      {paused ? (
        <button className={BUTTON_CLASS} onClick={onResume} disabled={!canResume(state)}>
          Resume
        </button>
      ) : (
        <button className={BUTTON_CLASS} onClick={onPause} disabled={!canPause(state)}>
          Pause
        </button>
      )}

      <button className={BUTTON_CLASS} onClick={onReset} disabled={!canReset(state)}>
        Reset
      </button>

      <label className="ml-2 flex items-center gap-1 text-sm text-slate-400">
        Speed
        <select
          className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
          value={state.speed}
          disabled={!canSetSpeed(state)}
          onChange={(e) => onSpeedChange(Number(e.target.value))}
        >
          {SPEED_OPTIONS.map((multiplier) => (
            <option key={multiplier} value={multiplier}>
              {multiplier}x
            </option>
          ))}
        </select>
      </label>

      {state.error && <span className="ml-2 text-sm text-red-400">{state.error}</span>}
    </div>
  );
}
