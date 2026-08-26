"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useReducer, useState } from "react";

import { AgentDetailDrawer } from "@/components/AgentDetailDrawer";
import { EventStream } from "@/components/EventStream";
import { MetricsPanel } from "@/components/MetricsPanel";
import { ReplayControlBar } from "@/components/ReplayControlBar";
import { initialReplayControlState, replayControlReducer } from "@/lib/replay/controlReducer";
import { useReplayStream } from "@/lib/replay/useReplayStream";

// Sigma touches WebGL2RenderingContext at module load -- browser-only, same
// as app/page.tsx's own NetworkGraph import.
const NetworkGraph = dynamic(
  () => import("@/components/NetworkGraph").then((mod) => mod.NetworkGraph),
  { ssr: false },
);

// Keyed by experimentId in the parent so navigating to a different replay
// target remounts fresh -- useReplayStream relies on this, mirroring
// ExperimentView's own remount-by-key convention (app/page.tsx).
function ReplayContent({ experimentId }: { experimentId: string }) {
  const [control, dispatch] = useReducer(replayControlReducer, initialReplayControlState);
  const { state, loading, error, incomplete, totalEvents, playedCount, seek } = useReplayStream(
    experimentId,
    control.speed,
    control.playing,
  );
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const selectedNode = selectedAgentId ? (state.nodes.get(selectedAgentId) ?? null) : null;
  const incidents = selectedAgentId ? (state.incidentsByAgent.get(selectedAgentId) ?? []) : [];

  if (loading) {
    return <p className="p-4 text-sm text-slate-400">Loading replay…</p>;
  }
  if (error) {
    return <p className="p-4 text-sm text-red-400">Failed to load replay: {error}</p>;
  }

  return (
    <>
      {incomplete && (
        <div className="shrink-0 border-b border-amber-900 bg-amber-950 px-4 py-2 text-sm text-amber-300">
          This run is marked incomplete — persistence detected a gap, or the
          process never finalized it. Replay shows only what was actually
          recorded; treat its metrics as partial, not a trustworthy final
          result.
        </div>
      )}

      <div className="flex flex-1 overflow-visible">
        <MetricsPanel state={state} />
        <section className="min-h-[260px] flex-1 overflow-hidden">
          <NetworkGraph state={state} onNodeClick={setSelectedAgentId} />
        </section>
      </div>

      <AgentDetailDrawer
        node={selectedNode}
        edges={state.edges}
        incidents={incidents}
        onClose={() => setSelectedAgentId(null)}
      />

      <ReplayControlBar
        control={control}
        dispatch={dispatch}
        totalEvents={totalEvents}
        playedCount={playedCount}
        onSeek={seek}
      />

      <footer className="h-56 shrink-0 border-t border-slate-800">
        <EventStream events={state.recentEvents} />
      </footer>
    </>
  );
}

export default function ReplayPage(props: PageProps<"/history/[id]">) {
  const { id } = use(props.params);

  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold">AgentNet — Replay</h1>
          <p className="font-mono text-xs text-slate-500">{id}</p>
        </div>
        <Link href="/history" className="text-sm text-slate-400 hover:text-slate-200">
          ← Back to history
        </Link>
      </header>
      <ReplayContent key={id} experimentId={id} />
    </main>
  );
}
