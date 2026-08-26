import type { EdgeView, Event, NodeView } from "@/lib/stream/reducer";

export function deriveNeighbors(nodeId: string, edges: EdgeView[]): string[] {
  return edges
    .filter((e) => e.source === nodeId || e.target === nodeId)
    .map((e) => (e.source === nodeId ? e.target : e.source));
}

export function describeCompromisedBy(node: NodeView): string {
  const isCompromisedOrQuarantined =
    node.security_state === "compromised" || node.security_state === "quarantined";
  if (!isCompromisedOrQuarantined) {
    return "—";
  }
  if (node.compromised_by != null) {
    return node.compromised_by;
  }
  // The seeded initial compromise (BRIEF's "patient zero") genuinely has no
  // source agent — tick_compromised === 0 is how build_world() marks it —
  // so it's a known fact, not data lost before this session connected.
  if (node.tick_compromised === 0) {
    return "— (initial compromise)";
  }
  return "unknown (before this session's connection)";
}

export function AgentDetailDrawer({
  node,
  edges,
  incidents,
  onClose,
}: {
  node: NodeView | null;
  edges: EdgeView[];
  incidents: Event[];
  onClose: () => void;
}) {
  if (node === null) {
    return null;
  }

  const isCompromisedOrQuarantined =
    node.security_state === "compromised" || node.security_state === "quarantined";
  const tickCompromised =
    isCompromisedOrQuarantined && node.compromised_by == null && node.tick_compromised !== 0
      ? "unknown (before this session's connection)"
      : (node.tick_compromised ?? "—");
  const neighbors = deriveNeighbors(node.id, edges);

  return (
    <aside className="h-64 shrink-0 overflow-y-auto border-t border-slate-800 p-4 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-medium text-slate-300">Agent detail</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
        >
          Close
        </button>
      </div>

      <dl className="space-y-1 text-slate-400">
        <div className="flex justify-between">
          <dt>id</dt>
          <dd className="font-mono">{node.id}</dd>
        </div>
        <div className="flex justify-between">
          <dt>security_state</dt>
          <dd className="font-mono">{node.security_state}</dd>
        </div>
        <div className="flex justify-between">
          <dt>software_type</dt>
          <dd className="font-mono">{node.software_type}</dd>
        </div>
        <div className="flex justify-between">
          <dt>neighbors</dt>
          <dd className="font-mono">{neighbors.length > 0 ? neighbors.join(", ") : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Compromised by</dt>
          <dd className="font-mono">{describeCompromisedBy(node)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Tick compromised</dt>
          <dd className="font-mono">{tickCompromised}</dd>
        </div>
      </dl>

      <h3 className="mb-1 mt-3 font-medium text-slate-300">Incidents</h3>
      <p className="mb-2 text-xs text-slate-500">Showing this session&apos;s observed events only</p>

      {incidents.length === 0 ? (
        <p className="text-sm text-slate-500">No incidents observed for this agent.</p>
      ) : (
        <div className="font-mono text-xs">
          {incidents.map((event) => (
            <div
              key={event.event_id}
              className="flex items-baseline gap-3 border-b border-slate-800 py-1"
            >
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
      )}
    </aside>
  );
}
