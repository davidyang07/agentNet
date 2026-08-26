"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listExperiments, type ExperimentListItem } from "@/lib/api/client";

type StatusFilter = "all" | "finished" | "stopped" | "incomplete";
type DefenseFilter = "all" | "true" | "false";

const BUTTON_CLASS =
  "rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

function toListParams(status: StatusFilter, defenseEnabled: DefenseFilter) {
  return {
    status: status === "all" ? undefined : status,
    defenseEnabled: defenseEnabled === "all" ? undefined : defenseEnabled === "true",
  };
}

// Keyed by `${status}-${defenseEnabled}` in the parent so a filter change
// remounts this fresh -- mirrors ExperimentView's remount-by-key convention
// (app/page.tsx) and, like useReplayStream, keeps the mount effect's only
// setState calls inside the fetch's resolution callbacks rather than
// synchronously at the top (react-hooks/set-state-in-effect).
function HistoryList({
  status,
  defenseEnabled,
  selected,
  onToggleSelect,
}: {
  status: StatusFilter;
  defenseEnabled: DefenseFilter;
  selected: string[];
  onToggleSelect: (id: string) => void;
}) {
  const [items, setItems] = useState<ExperimentListItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listExperiments(toListParams(status, defenseEnabled)).then(
      (resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setNextCursor(resp.next_cursor);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
    // status/defenseEnabled are fixed props for this component's lifetime --
    // the parent remounts it (via `key`) when a filter changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadMore() {
    if (!nextCursor) return;
    setLoading(true);
    try {
      const resp = await listExperiments({ ...toListParams(status, defenseEnabled), cursor: nextCursor });
      setItems((prev) => [...prev, ...resp.items]);
      setNextCursor(resp.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (error) {
    return <p className="px-4 py-2 text-sm text-red-400">{error}</p>;
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-slate-950 text-slate-400">
          <tr className="border-b border-slate-800">
            <th className="w-8 px-4 py-2" />
            <th className="px-4 py-2">Created</th>
            <th className="px-4 py-2">Seed</th>
            <th className="px-4 py-2">Nodes</th>
            <th className="px-4 py-2">Defense</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Integrity</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.experiment_id} className="border-b border-slate-900">
              <td className="px-4 py-2">
                <input
                  type="checkbox"
                  checked={selected.includes(item.experiment_id)}
                  onChange={() => onToggleSelect(item.experiment_id)}
                  aria-label={`Select ${item.experiment_id} for comparison`}
                />
              </td>
              <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-400">
                {new Date(item.created_at).toLocaleString()}
              </td>
              <td className="px-4 py-2 font-mono">{item.seed}</td>
              <td className="px-4 py-2 font-mono">{item.config.node_count}</td>
              <td className="px-4 py-2 font-mono">{item.config.defense_enabled ? "on" : "off"}</td>
              <td className="px-4 py-2 font-mono">{item.final_status ?? "running/unknown"}</td>
              <td className="px-4 py-2">
                {item.is_complete === true ? (
                  <span className="text-emerald-400">complete</span>
                ) : (
                  <span className="text-amber-400">incomplete</span>
                )}
              </td>
              <td className="px-4 py-2">
                <Link
                  href={`/history/${item.experiment_id}`}
                  className="text-slate-300 underline hover:text-slate-100"
                >
                  Replay
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {items.length === 0 && !loading && (
        <p className="px-4 py-6 text-sm text-slate-500">No persisted experiments yet.</p>
      )}

      {nextCursor && (
        <div className="px-4 py-3">
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => void loadMore()}
            disabled={loading}
          >
            {loading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [defenseEnabled, setDefenseEnabled] = useState<DefenseFilter>("all");
  // Selection for comparison -- at most two, FIFO eviction on a third pick,
  // deliberately a plain list rather than a Set for stable A/B ordering.
  const [selected, setSelected] = useState<string[]>([]);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  }

  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
        <h1 className="text-lg font-semibold">AgentNet — History</h1>
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← Back to live
        </Link>
      </header>

      <div className="flex shrink-0 items-center gap-3 border-b border-slate-800 px-4 py-2 text-sm">
        <label className="flex items-center gap-1 text-slate-400">
          Status
          <select
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            <option value="all">all</option>
            <option value="finished">finished</option>
            <option value="stopped">stopped</option>
            <option value="incomplete">incomplete</option>
          </select>
        </label>
        <label className="flex items-center gap-1 text-slate-400">
          Defense
          <select
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
            value={defenseEnabled}
            onChange={(e) => setDefenseEnabled(e.target.value as DefenseFilter)}
          >
            <option value="all">all</option>
            <option value="true">on</option>
            <option value="false">off</option>
          </select>
        </label>

        {selected.length === 2 && (
          <Link
            href={`/history/compare?a=${selected[0]}&b=${selected[1]}`}
            className={`ml-auto ${BUTTON_CLASS}`}
          >
            Compare selected (2)
          </Link>
        )}
      </div>

      <HistoryList
        key={`${status}-${defenseEnabled}`}
        status={status}
        defenseEnabled={defenseEnabled}
        selected={selected}
        onToggleSelect={toggleSelect}
      />
    </main>
  );
}
