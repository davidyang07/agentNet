import type { Dispatch } from "react";

import type { ReplayControlAction, ReplayControlState } from "@/lib/replay/controlReducer";

const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 4, 8];

const BUTTON_CLASS =
  "rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

// Visually mirrors ControlBar, but wired to useReplayStream's local
// setters directly -- no pending/optimistic-update machinery, since
// there's no request latency to hide (docs/PHASE_1_5_PLAN.md §7).
export function ReplayControlBar({
  control,
  dispatch,
  totalEvents,
  playedCount,
  onSeek,
}: {
  control: ReplayControlState;
  dispatch: Dispatch<ReplayControlAction>;
  totalEvents: number;
  playedCount: number;
  onSeek: (index: number) => void;
}) {
  const finished = totalEvents > 0 && playedCount >= totalEvents;

  return (
    <div className="flex shrink-0 items-center gap-3 border-t border-slate-800 px-4 py-2 text-sm">
      <button
        type="button"
        className={BUTTON_CLASS}
        onClick={() => dispatch({ type: "toggle_play" })}
        disabled={totalEvents === 0 || finished}
      >
        {control.playing ? "Pause" : "Play"}
      </button>

      <button
        type="button"
        className={BUTTON_CLASS}
        onClick={() => {
          dispatch({ type: "pause" });
          onSeek(0);
        }}
      >
        Reset
      </button>

      <label className="flex items-center gap-1 text-slate-400">
        Speed
        <select
          className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
          value={control.speed}
          onChange={(e) => dispatch({ type: "set_speed", speed: Number(e.target.value) })}
        >
          {SPEED_OPTIONS.map((multiplier) => (
            <option key={multiplier} value={multiplier}>
              {multiplier}x
            </option>
          ))}
        </select>
      </label>

      <input
        type="range"
        min={0}
        max={totalEvents}
        value={playedCount}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="flex-1"
        aria-label="Scrub replay position"
        disabled={totalEvents === 0}
      />
      <span className="w-20 shrink-0 text-right font-mono text-slate-500">
        {playedCount} / {totalEvents}
      </span>
    </div>
  );
}
