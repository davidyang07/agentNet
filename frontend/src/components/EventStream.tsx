import type { GraphState } from "@/lib/stream/reducer";

export function EventStream({ events }: { events: GraphState["recentEvents"] }) {
  if (events.length === 0) {
    return <p className="p-3 text-sm text-slate-500">Waiting for events…</p>;
  }

  return (
    <div className="h-full overflow-y-auto font-mono text-xs">
      {[...events].reverse().map((event) => (
        <div
          key={event.event_id}
          className="flex items-baseline gap-3 border-b border-slate-800 px-3 py-1"
        >
          <span className="w-14 shrink-0 text-slate-500">#{event.seq}</span>
          <span className="w-14 shrink-0 text-slate-500">t={event.sim_tick}</span>
          <span className="w-48 shrink-0 text-slate-200">{event.event_type}</span>
          <span className="w-40 shrink-0 text-slate-400">
            {event.source_agent_id ?? "—"} → {event.target_agent_id ?? "—"}
          </span>
          {event.metadata && Object.keys(event.metadata).length > 0 && (
            <span className="truncate text-slate-500">{JSON.stringify(event.metadata)}</span>
          )}
        </div>
      ))}
    </div>
  );
}
